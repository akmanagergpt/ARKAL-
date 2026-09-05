"""F-0078 (`PRODUCTION_FACTORY_ATTEMPT_OBSERVABILITY_GAP`). Real proof that
`scripts/run_factory_worker.py` -- the actual production Factory worker,
not the manual `run_staged_generation.py` verification track -- now wires
the same F-0070 per-attempt observability wrapper and preserves
`last_raw_output` on terminal `STAGE_FAILED`.

Diagnostic provenance only. This is not a repair or convergence fix: no
checker, prompt, retry budget, anti-loop, or fingerprint logic is touched.
`main()` itself is not exercised here (it requires a real Ollama endpoint
and mutates the real `var/factory`/`var/command_center.db` state, exactly
the reason `test_run_staged_generation_wiring.py` already tests its own
sibling script by source order/presence rather than execution) -- the
wrapper class and the composition wiring around it are proven directly,
mirroring `test_stage_attempt_observability.py`'s own established pattern
for `run_staged_generation.py`'s identical `_ObservedModel`.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

from arkali.engineering.factory.component_generation import generate_staged_model_product
from arkali.engineering.factory.generation_stages import StageVocabulary
from arkali.engineering.localai.adapter import HonestState
from tests.engineering.test_component_generation import (
    _blueprint,
    _factory,
    _happy_path_queues,
    _output,
    _QueueModel,
    _workspace,
    REPO,
)

SCRIPT = REPO / "scripts" / "run_factory_worker.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _module():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("run_factory_worker", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# -- wiring proof (source-level, matching test_run_staged_generation_wiring.py) --


def test_model_factory_wraps_the_real_adapter_in_observed_model() -> None:
    source = _source()
    model_factory = source[
        source.index("def model_factory("): source.index("try:\n        result = generate_staged_model_product")
    ]
    assert "_ObservedModel(adapter, candidate_id, provider_model)" in model_factory
    assert "return observed, " in model_factory


def test_terminal_stage_failed_payload_preserves_last_raw_output() -> None:
    source = _source()
    stage_failed_block = source[
        source.index('except ModelGenerationError as error:'):
        source.index("ledger.record_state(\n            candidate_id, STAGE_FAILED")
    ]
    assert '"last_raw_output": getattr(error, "last_raw_output", "")' in stage_failed_block


def test_only_one_freeze_function_exists_no_second_evidence_store() -> None:
    """REUSE, never CREATE: `_ObservedModel.record_attempt` must call THIS
    script's own already-existing `_freeze()`, not a second one."""
    source = _source()
    assert source.count("def _freeze(") == 1
    observed_model_block = source[
        source.index("def record_attempt("): source.index("def _claim_one_job(")
    ]
    assert observed_model_block.count("_freeze(\n") == 1


def test_observed_model_is_private_no_new_public_symbol() -> None:
    module = _module()
    assert not hasattr(module, "ObservedModel")  # never promoted to public
    assert hasattr(module, "_ObservedModel")


# -- `_ObservedModel` itself: zero behavior change, real evidence capture --


class _FakeInner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0):
        self.calls.append((model_id, prompt, timeout_seconds))
        return "real-inference-result"


def test_infer_delegates_unchanged_through_the_observed_model_wrapper() -> None:
    module = _module()
    inner = _FakeInner()
    observed = module._ObservedModel(inner, "factory-goal-test", "ollama/test-model")
    result = observed.infer("test-model", "a real prompt", timeout_seconds=42.0)
    assert result == "real-inference-result"
    assert inner.calls == [("test-model", "a real prompt", 42.0)]


def test_the_observed_model_freezes_the_exact_real_attempt_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    captured: list[tuple] = []

    def fake_freeze(payload, task_id, context_hash, evidence, provider_model):  # noqa: ANN001
        captured.append((payload, task_id, context_hash, evidence, provider_model))
        return context_hash

    monkeypatch.setattr(module, "_freeze", fake_freeze)
    observed = module._ObservedModel(_FakeInner(), "factory-goal-test", "ollama/qwen2.5-coder:14b")
    observed.record_attempt(
        "product_ux_spec", 2, "default", "the real retry prompt", "the real raw output",
        (("ux_spec_missing_module", "product/ux_spec.json", "a real detail"),), "some-fingerprint",
    )
    assert len(captured) == 1
    payload, task_id, context_hash, evidence, provider_model = captured[0]
    body = json.loads(payload)
    assert body["candidate_id"] == "factory-goal-test"
    assert body["stage"] == "product_ux_spec"
    assert body["attempt_number"] == 2
    assert body["prompt"] == "the real retry prompt"
    assert body["raw_output"] == "the real raw output"
    assert body["findings"] == [
        {"code": "ux_spec_missing_module", "path": "product/ux_spec.json", "detail": "a real detail"},
    ]
    assert body["fingerprint"] == "some-fingerprint"
    assert task_id == "factory-goal-test"
    assert provider_model == "ollama/qwen2.5-coder:14b"
    assert "F-0070" in evidence[0]
    assert "F-0078" in evidence[0]


def test_a_failure_inside_record_attempt_never_aborts_or_alters_generation(
    tmp_path: pathlib.Path,
) -> None:
    """The same failure-safety property F-0070 already proves generically
    (`_notify_attempt` catches and warns, never propagates) -- proven here
    against THIS script's own concrete `_ObservedModel`, not a test double."""
    module = _module()

    class _RaisingObservedModel(module._ObservedModel):
        def record_attempt(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated diagnostic-hook failure")

    class _QueueInner:
        def __init__(self, outcomes: list[tuple[HonestState, str]]) -> None:
            self._outcomes = list(outcomes)

        def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0):
            from arkali.engineering.localai.adapter import InferenceResult

            state, output = self._outcomes.pop(0)
            return InferenceResult(
                runtime="test-runtime", model_id=model_id, state=state,
                detail="queued", output=output, output_excerpt=output[:200],
            )

    queues = _happy_path_queues()
    models: dict[str, object] = {}

    def factory(stage_name: str):  # noqa: ANN202
        if stage_name not in models:
            models[stage_name] = _RaisingObservedModel(
                _QueueInner(queues[stage_name]), "factory-goal-test", "ollama/test-model",
            )
        return models[stage_name], "test-model"

    with pytest.warns(RuntimeWarning, match="F-0070 attempt-observability hook failed"):
        result = generate_staged_model_product(
            _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
        )
    assert result.attempts_used == 11


def test_evidence_capture_reflects_a_real_retry_including_previous_attempt_output(
    tmp_path: pathlib.Path,
) -> None:
    """End-to-end proof (F-0077 + F-0078 together, through THIS script's
    own concrete `_ObservedModel`): attempt 2's own recorded evidence
    includes the F-0077 `previous_attempt_output` field inside its own
    real prompt, and attempt 1's own real rejected output is recoverable
    from attempt 2's own frozen evidence -- never lost, never a substring
    test of the mechanism alone."""
    module = _module()
    recorded: list[dict] = []

    class _RecordingObservedModel(module._ObservedModel):
        def record_attempt(
            self, stage_name, attempt_number, repair_strategy, prompt, raw_output,
            findings, fingerprint,
        ) -> None:
            recorded.append({
                "stage": stage_name, "attempt_number": attempt_number,
                "repair_strategy": repair_strategy, "prompt": prompt,
                "raw_output": raw_output, "findings": findings, "fingerprint": fingerprint,
            })

    class _QueueInner:
        def __init__(self, outcomes: list[tuple[HonestState, str]]) -> None:
            self._outcomes = list(outcomes)

        def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0):
            from arkali.engineering.localai.adapter import InferenceResult

            state, output = self._outcomes.pop(0)
            return InferenceResult(
                runtime="test-runtime", model_id=model_id, state=state,
                detail="queued", output=output, output_excerpt=output[:200],
            )

    queues = _happy_path_queues()
    bad = _output({"backend/main.py": "app = object()\n"})
    good = queues["backend_cors_boundary"][0]
    queues["backend_cors_boundary"] = [(HonestState.PASS, bad), good]

    def factory(stage_name: str):  # noqa: ANN202
        return _RecordingObservedModel(
            _QueueInner(queues[stage_name]), "factory-goal-test", "ollama/test-model",
        ), "test-model"

    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    cors_attempts = [a for a in recorded if a["stage"] == "backend_cors_boundary"]
    assert len(cors_attempts) == 2
    assert cors_attempts[0]["raw_output"] == bad
    # Attempt 2's own real prompt carries F-0077's own field, containing
    # attempt 1's own exact rejected output -- recoverable from evidence
    # that previously did not exist for this real production path at all.
    retry_prompt = json.loads(cors_attempts[1]["prompt"])
    assert retry_prompt["previous_attempt_output"] == {"backend/main.py": "app = object()\n"}
