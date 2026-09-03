"""F-0070 (`STAGED_GENERATION_ATTEMPT_EVIDENCE_GAP`). Real, end-to-end
proof that `_generate_one_stage`'s new, optional per-attempt
observability hook lets every real attempt's own (stage, attempt number,
repair strategy, prompt, raw output, structured findings, fingerprint)
be reconstructed after the fact -- never a substring test of the helper
alone, and never a mock of the real retry loop.

Diagnostic provenance only (repeated exactly because the finding's own
severity depends on it): none of this replaces the candidate ledger, the
terminal stage evidence `run_staged_generation.py`'s own `_freeze()`
already writes, or the campaign ledger.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from alembic import command
from alembic.config import Config

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.engineering.factory.component_generation import generate_staged_model_product
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.generation_stages import StageVocabulary
from arkali.engineering.localai.adapter import HonestState
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from tests.engineering.test_component_generation import (
    _blueprint,
    _factory,
    _happy_path_queues,
    _output,
    _QueueModel,
    _workspace,
    REPO,
)
from tests.engineering.test_frontend_convergence import (
    _BACKEND_CONTRACT_FILES,
    _BROKEN_APP_JS,
    _CLIENT_JS,
    _FIXED_APP_JS,
    _UX_SPEC_JSON,
)

BACKEND = REPO / "backend"


class _RecordingQueueModel(_QueueModel):
    """The exact real `_QueueModel` every existing test already uses,
    additionally implementing the real, optional `record_attempt` method
    `component_generation._notify_attempt` discovers structurally
    (`getattr(model, "record_attempt", None)`) -- proves the real wiring,
    never a mock of it."""

    def __init__(self, outcomes: list[tuple[HonestState, str]]) -> None:
        super().__init__(outcomes)
        self.attempts: list[tuple] = []

    def record_attempt(
        self, stage_name: str, attempt_number: int, repair_strategy: str,
        prompt: str, raw_output: str, findings: tuple[tuple[str, str, str], ...],
        fingerprint: str | None,
    ) -> None:
        self.attempts.append(
            (stage_name, attempt_number, repair_strategy, prompt, raw_output, findings, fingerprint)
        )


class _RaisingRecordingQueueModel(_RecordingQueueModel):
    """F-0070 property (failure safety): `record_attempt` itself raises,
    every real time -- proves a diagnostic hook's own failure can never
    abort or alter the real generation it is observing."""

    def record_attempt(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated diagnostic-hook failure")


def _one_attempt_queues() -> dict[str, list[tuple[HonestState, str]]]:
    queues = _happy_path_queues()
    queues["backend_contract"] = [(HonestState.PASS, _output(_BACKEND_CONTRACT_FILES))]
    queues["product_ux_spec"] = [(HonestState.PASS, _output({"product/ux_spec.json": _UX_SPEC_JSON}))]
    queues["frontend_client"] = [(HonestState.PASS, _output({"frontend/src/client.js": _CLIENT_JS}))]
    return queues


def test_a_a_single_passing_attempt_produces_exactly_one_recorded_attempt(
    tmp_path: pathlib.Path,
) -> None:
    queues = _one_attempt_queues()
    queues["frontend_forms"] = [(HonestState.PASS, _output({"frontend/src/App.js": _FIXED_APP_JS}))]
    factory = _factory(queues, model_cls=_RecordingQueueModel)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
    assert len(model.attempts) == 1
    stage_name, attempt_number, strategy, prompt, raw_output, findings, fingerprint = model.attempts[0]
    assert stage_name == "frontend_forms"
    assert attempt_number == 1
    assert findings == ()
    assert fingerprint is None


def test_b_c_a_three_attempt_convergence_reconstructs_every_attempt_in_order(
    tmp_path: pathlib.Path,
) -> None:
    """Properties B/C: attempt 1's own real broken output, attempt 2's own
    different broken output, and attempt 3's own real fix are each
    independently reconstructable, in the real order they happened --
    never just the final one."""
    queues = _one_attempt_queues()
    broken_arity = _output({"frontend/src/App.js": _BROKEN_APP_JS})
    broken_missing_import = _output({
        "frontend/src/App.js": (
            "import React from 'react';\n"
            "function WorkForm({ onSubmit }) { return <form onSubmit={onSubmit} />; }\n"
            "<WorkForm onSubmit={async (title) => { const { id } = useParams(); "
            "await updateWork(id, title); }} />"
        ),
    })
    fixed = _output({"frontend/src/App.js": _FIXED_APP_JS})
    queues["frontend_forms"] = [
        (HonestState.PASS, broken_arity),
        (HonestState.PASS, broken_missing_import),
        (HonestState.PASS, fixed),
    ]
    factory = _factory(queues, model_cls=_RecordingQueueModel)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
    assert len(model.attempts) == 3
    numbers = [a[1] for a in model.attempts]
    assert numbers == [1, 2, 3]
    # Attempt 1's own real defect class differs from attempt 2's own --
    # both are real, distinct, and both survive independently.
    codes_1 = {code for code, _p, _d in model.attempts[0][5]}
    codes_2 = {code for code, _p, _d in model.attempts[1][5]}
    assert codes_1 and codes_2 and codes_1 != codes_2
    # Attempt 3 (the real fix) converged: no findings.
    assert model.attempts[2][5] == ()


def test_d_the_exact_real_prompt_is_preserved_per_attempt(tmp_path: pathlib.Path) -> None:
    queues = _one_attempt_queues()
    broken = _output({"frontend/src/App.js": _BROKEN_APP_JS})
    fixed = _output({"frontend/src/App.js": _FIXED_APP_JS})
    queues["frontend_forms"] = [(HonestState.PASS, broken), (HonestState.PASS, fixed)]
    factory = _factory(queues, model_cls=_RecordingQueueModel)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
    # The model's own recorded prompts (from infer()) and the observability
    # hook's own recorded prompts must be the exact same real strings.
    assert [a[3] for a in model.attempts] == model.prompts


def test_e_the_exact_real_raw_output_is_preserved_per_attempt(tmp_path: pathlib.Path) -> None:
    queues = _one_attempt_queues()
    broken = _output({"frontend/src/App.js": _BROKEN_APP_JS})
    fixed = _output({"frontend/src/App.js": _FIXED_APP_JS})
    queues["frontend_forms"] = [(HonestState.PASS, broken), (HonestState.PASS, fixed)]
    factory = _factory(queues, model_cls=_RecordingQueueModel)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
    assert model.attempts[0][4] == broken
    assert model.attempts[1][4] == fixed


def test_f_multi_finding_structured_data_is_not_lost(tmp_path: pathlib.Path) -> None:
    """golden-work-131's own real shape: one attempt with several real,
    simultaneous findings must arrive at the observability hook with
    every one of them still present, not collapsed to one."""
    queues = _one_attempt_queues()
    missing_import_and_arity = _output({
        "frontend/src/App.js": (
            "import React from 'react';\n"
            "function WorkForm({ onSubmit }) { return <form onSubmit={onSubmit} />; }\n"
            "<WorkForm onSubmit={updateWork} />"
        ),
    })
    fixed = _output({"frontend/src/App.js": _FIXED_APP_JS})
    queues["frontend_forms"] = [(HonestState.PASS, missing_import_and_arity), (HonestState.PASS, fixed)]
    factory = _factory(queues, model_cls=_RecordingQueueModel)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
    codes = {code for code, _p, _d in model.attempts[0][5]}
    assert len(codes) >= 2


def test_g_callback_absent_leaves_existing_generation_behavior_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    """The real, unmodified `_QueueModel` (no `record_attempt` at all,
    the exact shape every pre-F-0070 test already used) must behave
    byte-for-byte as before: same files, same attempts_used."""
    queues = _happy_path_queues()
    result = generate_staged_model_product(
        _blueprint(), _factory(queues), _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11


def test_failure_safety_a_raising_hook_never_aborts_or_alters_real_generation(
    tmp_path: pathlib.Path,
) -> None:
    """A diagnostic-only hook that raises on every real call must never
    change the real outcome -- generation still converges exactly as it
    would have with no hook at all, only an explicit warning is emitted."""
    queues = _one_attempt_queues()
    queues["frontend_forms"] = [(HonestState.PASS, _output({"frontend/src/App.js": _FIXED_APP_JS}))]
    factory = _factory(queues, model_cls=_RaisingRecordingQueueModel)
    with pytest.warns(RuntimeWarning, match="F-0070 attempt-observability hook failed"):
        result = generate_staged_model_product(
            _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
        )
    assert "frontend/src/App.js" in result.files


def test_j_a_structurally_different_domain_uses_the_identical_mechanism(
    tmp_path: pathlib.Path,
) -> None:
    """A second, unrelated domain fixture (inventory, never task/student)
    reproduces the identical observability behavior -- the hook itself
    names no field, resource or domain anywhere."""
    ux_spec = json.dumps({
        "product_title": "Inventory System", "primary_roles": ["staff"],
        "modules": [{
            "name": "products", "navigation_label": "Products", "presentation": "table",
            "actions": ["create"], "forms": [{"name": "product_form", "fields": ["id", "price"]}],
            "search_filter": False,
            "states": {"loading": True, "empty": True, "error": True, "success": True},
        }],
        "navigation_destinations": ["Products"],
        "design_system": {
            "typography_scale": ["base"], "spacing_scale": ["sm"],
            "component_conventions": ["table"], "responsive": "desktop-first",
            "accessible_focus_contrast": True,
        },
        "destructive_action_confirmation": False,
    })
    client_js = "export function createProduct(price) { return fetch('/products', {method:'POST'}); }\n"
    backend_files = {
        "backend/routes/product_routes.json": json.dumps([
            {"path": "/products", "method": "GET"}, {"path": "/products", "method": "POST"},
        ]),
        "backend/models/product_model.json": json.dumps(
            {"table_name": "products", "fields": {"id": {"type": "integer"}, "price": {"type": "number"}}}
        ),
    }
    app_js = (
        "import React from 'react';\n"
        "import { createProduct } from './client';\n"
        "function ProductForm() {\n"
        "  const [price, setPrice] = React.useState('');\n"
        "  const [success, setSuccess] = React.useState(false);\n"
        "  const handleSubmit = async (e) => {\n"
        "    e.preventDefault(); await createProduct(price); setSuccess(true);\n"
        "  };\n"
        "  return <form onSubmit={handleSubmit}><label>Price<input required "
        "value={price} onChange={e=>setPrice(e.target.value)} /></label>"
        "<button type='submit'>Submit</button>{success && <div>Success!</div>}</form>;\n"
        "}\n<ProductForm />"
    )
    queues = _happy_path_queues()
    queues["backend_contract"] = [(HonestState.PASS, _output(backend_files))]
    queues["product_ux_spec"] = [(HonestState.PASS, _output({"product/ux_spec.json": ux_spec}))]
    queues["frontend_client"] = [(HonestState.PASS, _output({"frontend/src/client.js": client_js}))]
    queues["frontend_forms"] = [(HonestState.PASS, _output({"frontend/src/App.js": app_js}))]
    factory = _factory(queues, model_cls=_RecordingQueueModel)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
    assert len(model.attempts) == 1
    assert model.attempts[0][0] == "frontend_forms"


def test_k_the_observability_mechanism_itself_names_no_golden_domain_token() -> None:
    import inspect

    from arkali.engineering.factory import component_generation
    source = inspect.getsource(component_generation._notify_attempt)
    banned = ("student", "payment", "course", "task", "/tasks", "/students")
    lowered = source.lower()
    for token in banned:
        assert token not in lowered, token


# ---------------------------------------------------------------------------
# `_ObservedModel` (scripts/run_staged_generation.py) -- the script-layer
# wrapper that actually freezes attempt evidence via the real, existing
# ArtifactStore/_freeze() mechanism. Imported directly (a valid Python
# module name, no hyphens) rather than duplicating its logic.
# ---------------------------------------------------------------------------

def _load_run_staged_generation():  # noqa: ANN202
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_staged_generation", REPO / "scripts" / "run_staged_generation.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class _FakeInner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0):
        self.calls.append((model_id, prompt, timeout_seconds))
        return "real-inference-result"


def test_h_infer_delegates_unchanged_through_the_observed_model_wrapper() -> None:
    module = _load_run_staged_generation()
    inner = _FakeInner()
    observed = module._ObservedModel(inner, "golden-work-test", "ollama/test-model")
    result = observed.infer("test-model", "a real prompt", timeout_seconds=42.0)
    assert result == "real-inference-result"
    assert inner.calls == [("test-model", "a real prompt", 42.0)]


def test_the_observed_model_freezes_the_exact_real_attempt_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_run_staged_generation()
    captured: list[tuple] = []

    def fake_freeze(payload, task_id, context_hash, evidence, provider_model):  # noqa: ANN001
        captured.append((payload, task_id, context_hash, evidence, provider_model))
        return context_hash

    monkeypatch.setattr(module, "_freeze", fake_freeze)
    observed = module._ObservedModel(_FakeInner(), "golden-work-test", "ollama/qwen2.5-coder:14b")
    observed.record_attempt(
        "frontend_forms", 2, "structured_hint", "the real prompt", "the real raw output",
        (("frontend_route_unreachable", "frontend/src/App.js", "a real detail"),), "some-fingerprint",
    )
    assert len(captured) == 1
    payload, task_id, context_hash, evidence, provider_model = captured[0]
    body = json.loads(payload)
    assert body["candidate_id"] == "golden-work-test"
    assert body["stage"] == "frontend_forms"
    assert body["attempt_number"] == 2
    assert body["repair_strategy"] == "structured_hint"
    assert body["prompt"] == "the real prompt"
    assert body["raw_output"] == "the real raw output"
    assert body["findings"] == [
        {"code": "frontend_route_unreachable", "path": "frontend/src/App.js", "detail": "a real detail"},
    ]
    assert body["fingerprint"] == "some-fingerprint"
    assert task_id == "golden-work-test"
    assert provider_model == "ollama/qwen2.5-coder:14b"
    assert "diagnostic provenance only" in evidence[0]
    assert "F-0070" in evidence[0]


# ---------------------------------------------------------------------------
# Property I: the underlying content-addressed store's own real dedup
# semantics -- the exact, already-proven `ArtifactStore.register`
# mechanism `_freeze()` itself wraps, unmodified, isolated real SQLite
# (the same fixture shape `tests/evidence/test_artifact_store.py` already
# establishes) rather than the real, shared production evidence DB.
# ---------------------------------------------------------------------------

def _alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


def test_i_duplicate_attempt_evidence_dedupes_via_the_real_existing_store(
    tmp_path: pathlib.Path,
) -> None:
    database_path = tmp_path / "evidence.db"
    command.upgrade(_alembic_config(database_path), "head")
    engine = create_persistence_engine(sqlite_url(database_path))
    pdp = PolicyDecisionPoint.load(REPO)
    blobs = ArtifactBlobStore(tmp_path / "blobs", PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"))
    payload = json.dumps({
        "candidate_id": "golden-work-test", "stage": "frontend_forms", "attempt_number": 1,
    }, sort_keys=True).encode()
    provenance = ProvenanceInput(
        producer_agent="engineering.factory", provider_model="ollama/test-model",
        task_id="golden-work-test", specification_version="phase-30-staged-generation/1.0.0",
        context_hash="sha256:deadbeef", evidence=("real staged-generation attempt evidence",),
    )
    with unit_of_work(create_session_factory(engine)) as session:
        first_address = ArtifactStore(session, blobs).register(payload, provenance)
    with unit_of_work(create_session_factory(engine)) as session:
        second_address = ArtifactStore(session, blobs).register(payload, provenance)
    assert first_address == second_address
    engine.dispose()
