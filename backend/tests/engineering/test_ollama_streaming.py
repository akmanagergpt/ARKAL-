from __future__ import annotations

import io
import json
import urllib.request

from arkali.engineering.localai.adapter import HonestState
from arkali.engineering.localai.ollama_adapter import OllamaAdapter


class _Stream:
    status = 200

    def __init__(self, events: list[dict[str, object]], failure: Exception | None = None) -> None:
        self._lines = io.BytesIO(b"".join(json.dumps(event).encode() + b"\n" for event in events))
        self._failure = failure

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def readline(self) -> bytes:
        line = self._lines.readline()
        if not line and self._failure is not None:
            raise self._failure
        return line


def test_streamed_fragments_form_one_exact_completion(monkeypatch) -> None:  # noqa: ANN001
    stream = _Stream([
        {"response": "{\"files\":", "done": False},
        {"response": "[]}", "done": False},
        {"response": "", "done": True, "done_reason": "stop", "eval_count": 2,
         "prompt_eval_count": 10},
    ])
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: stream)

    result = OllamaAdapter().infer("coder", "prompt", timeout_seconds=9)

    assert result.state is HonestState.PASS
    assert result.output == '{"files":[]}'
    assert result.completion is not None
    assert result.completion.finish_reason == "stop"
    assert result.completion.output_token_count == 2


def test_timeout_preserves_partial_output_as_non_pass_evidence(monkeypatch) -> None:  # noqa: ANN001
    stream = _Stream([{"response": "partial bytes", "done": False}], TimeoutError("stalled"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: stream)

    result = OllamaAdapter().infer("coder", "prompt", timeout_seconds=9)

    assert result.state is HonestState.NOT_CONFIGURED
    assert result.output == "partial bytes"
    assert result.output_excerpt == "partial bytes"
    assert "stalled" in result.detail


def test_no_output_timeout_remains_an_honest_non_pass(monkeypatch) -> None:  # noqa: ANN001
    stream = _Stream([], TimeoutError("no progress"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: stream)

    result = OllamaAdapter().infer("coder", "prompt", timeout_seconds=9)

    assert result.state is HonestState.NOT_CONFIGURED
    assert result.output == ""


def test_total_deadline_is_enforced_before_another_read(monkeypatch) -> None:  # noqa: ANN001
    stream = _Stream([{"response": "too late", "done": False}])
    ticks = iter((0.0, 0.0, 10.0, 10.0))
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: stream)
    monkeypatch.setattr("arkali.engineering.localai.ollama_adapter.time.monotonic",
                        lambda: next(ticks))

    result = OllamaAdapter().infer("coder", "prompt", timeout_seconds=5)

    assert result.state is HonestState.NOT_CONFIGURED
    assert result.output == ""
    assert "deadline exceeded" in result.detail
