"""Bounded local-model guidance for natural-language product intake.

The model may ask questions and propose a draft, but it cannot enqueue work,
derive an authoritative blueprint, or approve its own proposal.  The existing
Factory intake remains the only production boundary after explicit user
approval.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from arkali.engineering.localai.adapter import HonestState, LocalRuntimeAdapter


class IntakeMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class IntakeGuidance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    assistant_message: str = Field(min_length=1, max_length=4000)
    questions: tuple[str, ...] = Field(default=(), max_length=3)
    proposed_goal_text: str | None = Field(default=None, max_length=12000)


def _prompt(messages: Sequence[IntakeMessage]) -> str:
    history = [{"role": item.role, "content": item.content} for item in messages]
    return "\n".join((
        "You are ARKALI's Turkish product discovery assistant.",
        "Speak clear, friendly Turkish to a non-technical user.",
        "Ask at most three short questions at a time. Do not invent missing business rules.",
        "When the product is sufficiently clear, propose a compact numbered goal in English.",
        "That goal must state domain records, SQLite persistence, CRUD REST endpoints,",
        "a usable frontend with create/view/edit/delete, and measurable acceptance criteria.",
        "Keep UI complexity proportional to the need; never prescribe a large UI unnecessarily.",
        "Return JSON only with keys assistant_message, questions, proposed_goal_text.",
        "Use null for proposed_goal_text until the user has answered enough questions.",
        f"Conversation: {json.dumps(history, ensure_ascii=False)}",
    ))


def continue_intake_conversation(
    adapter: LocalRuntimeAdapter,
    model_id: str,
    messages: Sequence[IntakeMessage],
    *,
    timeout_seconds: float = 180.0,
) -> IntakeGuidance:
    """Run one bounded local guidance turn and validate its structured result."""
    if not messages or messages[-1].role != "user":
        raise ValueError("conversation must end with a user message")
    result = adapter.infer(model_id, _prompt(messages), timeout_seconds=timeout_seconds)
    if result.state is not HonestState.PASS or not result.output.strip():
        raise RuntimeError(result.detail or "local guidance did not return output")
    try:
        return IntakeGuidance.model_validate(json.loads(result.output))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError("local guidance returned an invalid structured response") from exc


__all__ = ["IntakeGuidance", "IntakeMessage", "continue_intake_conversation"]
