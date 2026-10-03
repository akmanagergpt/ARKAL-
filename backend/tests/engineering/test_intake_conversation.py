from __future__ import annotations

import json

import pytest

from arkali.engineering.localai.adapter import HonestState, InferenceResult
from arkali.engineering.localai.intake_conversation import (
    IntakeMessage, continue_intake_conversation,
)


class _Adapter:
    runtime = "test-local"

    def __init__(self, output: str, state: HonestState = HonestState.PASS) -> None:
        self.output = output
        self.state = state
        self.calls: list[tuple[str, str, float]] = []

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0):
        self.calls.append((model_id, prompt, timeout_seconds))
        return InferenceResult(
            runtime=self.runtime, model_id=model_id, state=self.state,
            detail="test result", output=self.output,
        )


def test_guidance_is_turkish_structured_and_bounded() -> None:
    adapter = _Adapter(json.dumps({
        "assistant_message": "Kaç kişi görev alacak?",
        "questions": ["Kaç kişi görev alacak?"],
        "proposed_goal_text": None,
    }))
    guidance = continue_intake_conversation(
        adapter, "qwen2.5-coder:14b",
        (IntakeMessage(role="user", content="Görev takip programı istiyorum"),),
    )
    assert guidance.assistant_message == "Kaç kişi görev alacak?"
    assert guidance.proposed_goal_text is None
    assert adapter.calls[0][0] == "qwen2.5-coder:14b"
    assert adapter.calls[0][2] == 180.0
    assert "NEVER ask the user to choose a programming language" in adapter.calls[0][1]
    assert "SQLite persistence" in adapter.calls[0][1]
    assert "proposed_goal_text MUST be non-null" in adapter.calls[0][1]


def test_ready_draft_is_only_returned_for_user_approval() -> None:
    goal = "1. The system must persist tasks using SQLite with at least 1 table."
    adapter = _Adapter(json.dumps({
        "assistant_message": "Taslağınız hazır.", "questions": [],
        "proposed_goal_text": goal,
    }))
    guidance = continue_intake_conversation(
        adapter, "qwen2.5-coder:14b",
        (IntakeMessage(role="user", content="Tek kullanıcı olacak"),),
    )
    assert guidance.proposed_goal_text == goal


@pytest.mark.parametrize("output", ["", "not-json", "{}"])
def test_empty_or_invalid_model_output_never_becomes_a_draft(output: str) -> None:
    adapter = _Adapter(output)
    with pytest.raises(RuntimeError):
        continue_intake_conversation(
            adapter, "qwen2.5-coder:14b",
            (IntakeMessage(role="user", content="Bir uygulama istiyorum"),),
        )


def test_non_pass_inference_is_honest_failure() -> None:
    adapter = _Adapter("{}", HonestState.NOT_CONFIGURED)
    with pytest.raises(RuntimeError, match="test result"):
        continue_intake_conversation(
            adapter, "qwen2.5-coder:14b",
            (IntakeMessage(role="user", content="Bir uygulama istiyorum"),),
        )
