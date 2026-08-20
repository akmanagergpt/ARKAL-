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
    result = OllamaAdapter(json_mode=True).infer("coder", "prompt", timeout_seconds=9)

    assert captured["body"] == {
        "model": "coder",
        "prompt": "prompt",
        "stream": False,
        "format": "json",
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
