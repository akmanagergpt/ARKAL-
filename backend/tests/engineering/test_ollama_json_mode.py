from __future__ import annotations

import json
import urllib.request

from arkali.engineering.localai.ollama_adapter import OllamaAdapter


class _Response:
    status = 200

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @staticmethod
    def read() -> bytes:
        return b'{"response":"{}"}'


def test_json_mode_uses_ollama_native_structured_output(
    monkeypatch,
) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        captured["body"] = json.loads(bytes(request.data or b"{}"))
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = OllamaAdapter(json_mode=True, max_output_tokens=4096).infer(
        "coder", "prompt", timeout_seconds=9
    )

    assert captured["body"] == {
        "model": "coder",
        "prompt": "prompt",
        "stream": False,
        "format": "json",
        "options": {"num_ctx": 8192, "num_predict": 4096, "temperature": 0},
    }
    assert captured["timeout"] == 9
    assert result.output == "{}"


def test_default_adapter_does_not_force_runtime_specific_format(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        captured.update(json.loads(bytes(request.data or b"{}")))
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    OllamaAdapter().infer("coder", "prompt")

    assert "format" not in captured
    # golden-work-125 (real repository evidence): num_ctx is now ALWAYS
    # sent explicitly, regardless of max_output_tokens -- leaving it unset
    # let the real Ollama server on this host silently fall back to its
    # own OLLAMA_CONTEXT_LENGTH=4096 default instead of the model's real,
    # much larger capability, starving a dense real prompt of headroom.
    assert captured["options"] == {"num_ctx": 8192, "temperature": 0}


def test_num_ctx_leaves_real_headroom_for_a_dense_real_frontend_forms_prompt(
    monkeypatch,
) -> None:  # noqa: ANN001
    """golden-work-125 (real repository evidence): reconstructing its own
    real, final `frontend_forms` prompt (goal + requirements + the
    stage's own dense rule text + every visible prior file + the prior
    attempt's failure text) measured ~3274 tokens of input alone (a
    chars/4 estimate) -- against the real host's own
    OLLAMA_CONTEXT_LENGTH=4096 default and a `num_predict` request of
    4096, input and requested output were competing for the same,
    already-exhausted window. The default `num_ctx` here (8192) must
    leave real headroom for input this size plus a full-budget
    `num_predict=4096` output request, not just barely fit one alone."""
    captured: dict[str, object] = {}

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        captured.update(json.loads(bytes(request.data or b"{}")))
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    measured_real_input_tokens = 3274
    OllamaAdapter(max_output_tokens=4096).infer("coder", "x" * 100)

    options = captured["options"]
    assert options["num_ctx"] >= measured_real_input_tokens + options["num_predict"]
