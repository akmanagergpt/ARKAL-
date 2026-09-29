"""BIONIC_QWEN35_ARKALI_INTEGRATION: proves `OpenAICompatibleAdapter` (and
therefore Bionic's own OpenAI-compatible server) satisfies the exact same
`ModelSource`/`InferenceOutcome` structural Protocol `component_generation.
_generate_one_stage` already calls against `OllamaAdapter` -- through the
real, unmodified Factory stage-generation function itself, never a
hand-rolled substitute. No Factory file changes; the adapter's own
`infer()` already returns the same concrete `InferenceResult` type every
Factory caller reads.
"""

from __future__ import annotations

import json
import urllib.request

from arkali.engineering.factory.component_generation import _generate_one_stage
from arkali.engineering.factory.generation_stages import StageVocabulary
from arkali.engineering.localai.openai_compatible_adapter import OpenAICompatibleAdapter
from tests.engineering.test_component_generation import HAPPY_PATH_FILES, REPO, _blueprint


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


def test_the_real_backend_contract_stage_accepts_the_openai_compatible_adapter(
    monkeypatch,
) -> None:  # noqa: ANN001
    """The real `backend_contract` stage, driven end to end through the
    real, unmodified `_generate_one_stage`, with `OpenAICompatibleAdapter`
    standing in for Bionic. `HAPPY_PATH_FILES["backend_contract"]` is
    already a real, proven-valid stage output (golden-work-045, frozen
    evidence) -- reused verbatim as the mocked chat-completion content, so
    the real `backend_contract` checker's own real acceptance is what
    actually passes this test, not a hand-relaxed assertion."""
    files = HAPPY_PATH_FILES["backend_contract"]
    # `_generate_one_stage` expects the model's own raw output to be the
    # `{"files": [...]}` envelope directly -- the adapter's `infer()` already
    # extracts `choices[0].message.content` for us, so the mocked chat
    # completion's own content is that exact envelope, byte for byte.
    envelope = json.dumps({"files": [{"path": p, "content": c} for p, c in files.items()]})

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        body = json.dumps({
            "choices": [{"message": {"content": envelope}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }).encode()
        return _Response(body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    decl = StageVocabulary.load(REPO).stage("backend_contract")
    adapter = OpenAICompatibleAdapter()
    result = _generate_one_stage(
        decl, _blueprint(), adapter, "qwen/qwen3.5-9b", {},
        timeout_seconds=30.0, max_attempts=1,
    )

    assert result == files
