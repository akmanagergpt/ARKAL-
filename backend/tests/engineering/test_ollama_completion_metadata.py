"""F-0100 (`BACKEND_SCHEMA_TRUNCATED_GENERATION_GAP`), observability phase.

Real evidence (`goal-mtyeas61-75cn2k`, `backend_schema`): a genuinely
short, mid-construct-truncated real response left no way to tell whether
Ollama itself reported the generation as finished, or ARKALI's own read
path stopped early. `OllamaAdapter.infer()` already parses Ollama's full
non-streaming `/api/generate` response (`done`/`done_reason`/`eval_count`/
`prompt_eval_count` all present in that same JSON object) but previously
kept only `response` text, discarding the rest. This phase is
observational only: it proves the previously-discarded fields now reach
`InferenceResult.completion`, unbounded generation options and request
behaviour remain byte-for-byte unchanged.
"""

from __future__ import annotations

import json
import urllib.request

from arkali.engineering.localai.adapter import CompletionMetadata, InferenceResult
from arkali.engineering.localai.ollama_adapter import OllamaAdapter


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


def _ollama_reply(**fields: object) -> bytes:
    payload: dict[str, object] = {"response": "{}"}
    payload.update(fields)
    return json.dumps(payload).encode()


# -- A: a normal Ollama completion's own real fields are preserved ----------


def test_a_normal_stop_completion_metadata_is_preserved(monkeypatch) -> None:  # noqa: ANN001
    body = _ollama_reply(done=True, done_reason="stop", eval_count=135, prompt_eval_count=812)

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        return _Response(body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = OllamaAdapter().infer("coder", "prompt")

    assert result.completion == CompletionMetadata(
        completed=True, finish_reason="stop", output_token_count=135, prompt_token_count=812,
    )


# -- B: length-style completion metadata is preserved without acting on it --


def test_b_length_completion_metadata_is_preserved_without_changing_behavior(
    monkeypatch,
) -> None:  # noqa: ANN001
    body = _ollama_reply(done=True, done_reason="length", eval_count=4096, prompt_eval_count=200)
    captured: dict[str, object] = {}

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        captured["body"] = json.loads(bytes(request.data or b"{}"))
        return _Response(body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = OllamaAdapter(max_output_tokens=4096).infer("coder", "prompt")

    assert result.completion.finish_reason == "length"
    assert result.completion.output_token_count == 4096
    # The request itself carries no awareness of any prior completion --
    # this phase never feeds the new field back into a future call.
    assert captured["body"]["options"] == {"num_ctx": 8192, "num_predict": 4096, "temperature": 0}


# -- C: absent metadata remains backward-compatible --------------------------


def test_c_a_response_with_no_done_key_leaves_completion_none(monkeypatch) -> None:  # noqa: ANN001
    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        return _Response(b'{"response":"{}"}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = OllamaAdapter().infer("coder", "prompt")

    assert result.completion is None
    assert result.output == "{}"


# -- D: existing InferenceResult callers continue to work --------------------


def test_d_inference_result_constructs_without_completion() -> None:
    from arkali.kernel.contracts.honest_state import HonestState

    result = InferenceResult(
        runtime="test-runtime", model_id="m", state=HonestState.PASS, detail="d",
    )
    assert result.completion is None


# -- E/F: request payload and stream mode are unchanged ----------------------


def test_e_f_request_payload_and_stream_mode_are_unchanged(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        captured["body"] = json.loads(bytes(request.data or b"{}"))
        return _Response(_ollama_reply(done=True, done_reason="stop", eval_count=1, prompt_eval_count=1))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    OllamaAdapter(json_mode=True, max_output_tokens=4096).infer("coder", "prompt", timeout_seconds=9)

    assert captured["body"] == {
        "model": "coder", "prompt": "prompt", "stream": False, "format": "json",
        "options": {"num_ctx": 8192, "num_predict": 4096, "temperature": 0},
    }


# -- historical F-0100 evidence: no retrofit --------------------------------


def test_the_historical_f0100_artifact_carries_no_completion_metadata() -> None:
    """The real, frozen `goal-mtyeas61-75cn2k` evidence blob predates this
    fix -- its own call already discarded Ollama's completion facts, and
    nothing in this observability phase retrofits a guessed value onto it.
    Historical finish reason: UNKNOWN / NOT_RECORDED."""
    import pathlib

    blob = (
        pathlib.Path(__file__).resolve().parents[3]
        / "var" / "factory" / "evidence" / "blobs" / "sha256" / "8c"
        / "8cda9c6631d18066158c45573fad4940aba7fe0a1433123c5d2cef8b109cd575"
    )
    data = json.loads(blob.read_text(encoding="utf-8"))
    assert "last_completion_metadata" not in data
