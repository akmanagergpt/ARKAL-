"""BIONIC_QWEN35_ARKALI_INTEGRATION: `OpenAICompatibleAdapter.infer` did not
populate `InferenceResult.completion` at all (always `None`), unlike
`OllamaAdapter` -- this module's own docstring already anticipated exactly
this ("a future adapter reporting the same kind of fact under different
keys (e.g. an OpenAI-compatible `finish_reason`/`usage.completion_tokens`)
can populate this same shape"). These tests prove the real chat-completion
response's own `choices[0].finish_reason`/`usage.prompt_tokens`/
`usage.completion_tokens` now reach `InferenceResult.completion`, the same
generic shape every Factory caller already reads -- no adapter-specific
change anywhere outside this one file.
"""

from __future__ import annotations

import json
import urllib.request

from arkali.engineering.localai.adapter import CompletionMetadata, InferenceResult
from arkali.engineering.localai.openai_compatible_adapter import OpenAICompatibleAdapter


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _chat_reply(**fields: object) -> bytes:
    payload: dict[str, object] = {
        "choices": [{"message": {"content": "READY"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 14, "completion_tokens": 2},
    }
    payload.update(fields)
    return json.dumps(payload).encode()


# -- A: a normal "stop" completion's own real fields are preserved ----------


def test_a_normal_stop_completion_metadata_is_preserved(monkeypatch) -> None:  # noqa: ANN001
    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        return _Response(_chat_reply())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = OpenAICompatibleAdapter().infer("qwen/qwen3.5-9b", "prompt")

    assert result.completion == CompletionMetadata(
        completed=True, finish_reason="stop", output_token_count=2, prompt_token_count=14,
    )
    assert result.output == "READY"


# -- B: a "length"-truncated completion is preserved without acting on it ---


def test_b_length_completion_metadata_is_preserved_without_changing_behavior(
    monkeypatch,
) -> None:  # noqa: ANN001
    body = _chat_reply(
        choices=[{"message": {"content": ""}, "finish_reason": "length"}],
        usage={"prompt_tokens": 14, "completion_tokens": 10},
    )

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        return _Response(body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = OpenAICompatibleAdapter(max_output_tokens=10).infer("qwen/qwen3.5-9b", "prompt")

    assert result.completion.finish_reason == "length"
    assert result.completion.output_token_count == 10
    assert result.completion.prompt_token_count == 14
    assert result.output == ""


# -- C: no choices at all leaves completion honestly incomplete -------------


def test_c_a_response_with_no_choices_reports_incomplete_not_a_guess(monkeypatch) -> None:  # noqa: ANN001
    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        return _Response(json.dumps({"choices": [], "usage": {}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = OpenAICompatibleAdapter().infer("qwen/qwen3.5-9b", "prompt")

    assert result.output == ""
    assert result.completion.completed is False
    assert result.completion.finish_reason == ""


# -- D: existing InferenceResult callers continue to work --------------------


def test_d_inference_result_constructs_without_completion() -> None:
    from arkali.kernel.contracts.honest_state import HonestState

    result = InferenceResult(
        runtime="test-runtime", model_id="m", state=HonestState.PASS, detail="d",
    )
    assert result.completion is None
