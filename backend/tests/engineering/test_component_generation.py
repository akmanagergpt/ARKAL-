from __future__ import annotations

import json
import pathlib

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.blueprint_engine import derive_blueprint
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.factory.component_generation import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_STAGE_ATTEMPTS,
    _apply_deterministic_repairs,
    _backend_contract_findings,
    _backend_implementation_stage_findings,
    _cors_boundary_stage_findings,
    _frontend_forms_findings,
    _frontend_ui_findings,
    _generate_one_stage,
    _MAX_TIMEOUT_SCALE,
    _parse_stage_envelope,
    _REF_PROMPT_CHARS,
    _schema_only_findings,
    generate_staged_model_product,
)
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.generation_stages import StageVocabulary
from arkali.engineering.factory.stage_prompting import _stage_prompt
from arkali.engineering.localai.adapter import HonestState, InferenceResult

REPO = pathlib.Path(__file__).resolve().parents[3]
GOAL = """1. The system must persist task records using SQLite with at least 1 table.
2. The backend must expose at least 4 REST API endpoints for task management.
3. The frontend must display a task list within 1 screen.
4. The backend must respond within 500 ms for a single task request under normal load."""


def _blueprint():  # noqa: ANN202
    blueprint = derive_blueprint(GOAL, AuthorityMap.load(REPO))
    assert blueprint.is_fully_resolved
    return blueprint


def _workspace(tmp_path: pathlib.Path):  # noqa: ANN202
    stable = tmp_path / "stable"
    stable.mkdir()
    return WorkspaceAuthority(tmp_path / "candidates").allocate(
        workspace_id="staged-1", task_id="staged-1", agent_id="model-1",
        stable_snapshot=stable,
    )


class _QueueModel:
    """One `ModelSource` whose `infer` pops the next queued outcome."""

    def __init__(self, outcomes: list[tuple[HonestState, str]]) -> None:
        self._outcomes = list(outcomes)
        self.prompts: list[str] = []
        self.model_ids: list[str] = []
        self.timeouts: list[float] = []

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0) -> InferenceResult:
        self.prompts.append(prompt)
        self.model_ids.append(model_id)
        self.timeouts.append(timeout_seconds)
        state, output = self._outcomes.pop(0)
        return InferenceResult(
            runtime="test-runtime", model_id=model_id, state=state,
            detail="queued", output=output, output_excerpt=output[:200],
        )


def _factory(  # noqa: ANN202
    per_stage: dict[str, list[tuple[HonestState, str]]], *, model_cls: type = _QueueModel,
):
    """`model_cls` (F-0070): additive, defaults to the real `_QueueModel`
    every existing caller already used before this parameter existed --
    zero behavior change for any of them. A caller may pass a subclass
    (e.g. one that also implements the real, optional `record_attempt`
    hook `component_generation._notify_attempt` discovers structurally)
    to prove the real per-attempt observability wiring end to end."""
    models: dict[str, _QueueModel] = {}

    def factory(stage_name: str) -> tuple[_QueueModel, str]:
        if stage_name not in models:
            models[stage_name] = model_cls(per_stage[stage_name])
        return models[stage_name], "test-model"

    factory.models = models  # type: ignore[attr-defined]
    return factory


def _output(files: dict[str, str]) -> str:
    return json.dumps({"files": [{"path": p, "content": c} for p, c in files.items()]})


HAPPY_PATH_FILES: dict[str, dict[str, str]] = {
    # This exact shape is what a real qwen2.5-coder:14b produced unprompted
    # for this stage's rule (golden-work-045, frozen evidence
    # sha256:aabfc2e5f44758724d4941869eaccff28f3bfba18d76a5f39c044c32b7962eb5)
    # -- codified as the expected contract instead of a Python-decorator guess.
    "backend_contract": {
        "backend/routes/task_routes.json": json.dumps([
            {"path": "/works", "method": "GET", "model_fields": ["id", "title"]},
        ]),
        "backend/models/task_model.json": json.dumps(
            {"table_name": "works", "fields": {"id": {"type": "integer"}, "title": {"type": "string"}}}
        ),
    },
    "backend_schema": {
        "backend/schema.py": (
            "import sqlite3\ndef bootstrap():\n    sqlite3.connect('app.db').execute("
            "'CREATE TABLE IF NOT EXISTS works (id INTEGER)')\n"
        ),
    },
    "backend_implementation": {
        "backend/main.py": (
            "from backend.schema import bootstrap\nbootstrap()\n"
            "app = object()\n@app.get('/works')\ndef list_works():\n    return []\n"
            "class WorkRecord(object):\n    pass\n"
        ),
    },
    "backend_cors_boundary": {
        "backend/main.py": (
            "from flask_cors import CORS\n"
            "from backend.schema import bootstrap\nbootstrap()\n"
            "app = object()\nCORS(app)\n@app.get('/works')\ndef list_works():\n    return []\n"
            "class WorkRecord(object):\n    pass\n"
        ),
    },
    "backend_tests": {"tests/test_works.py": "def test_placeholder():\n    assert True\n"},
    "product_ux_spec": {
        "product/ux_spec.json": json.dumps({
            "product_title": "Work Tracker",
            "primary_roles": ["user"],
            "modules": [{
                "name": "works",
                "navigation_label": "Works",
                "presentation": "list",
                "actions": ["view"],
                "forms": [],
                "search_filter": False,
                "states": {"loading": True, "empty": True, "error": True, "success": False},
            }],
            "navigation_destinations": ["Works"],
            "design_system": {
                "typography_scale": ["base"],
                "spacing_scale": ["sm"],
                "component_conventions": ["list"],
                "responsive": "desktop-first",
                "accessible_focus_contrast": True,
            },
            "destructive_action_confirmation": True,
        }),
    },
    "frontend_client": {
        "frontend/src/client.js": "export function fetchWorks() { return fetch('/works'); }\n",
    },
    "frontend_ui": {
        "frontend/src/App.js": (
            "import { fetchWorks } from './client';\n"
            "function App() { fetchWorks(); return <button onClick={fetchWorks}>retry loading empty error works</button>; }\n"
            "export default App;\n"
        ),
        "frontend/src/index.js": (
            "import App from './App';\n"
            "ReactDOM.render(App, document.getElementById('root'));\n"
        ),
    },
    # The happy-path ux_spec's one module declares only "view" -- no
    # create/edit/delete -- so frontend_forms has nothing to add and
    # returns frontend_ui's own file back unchanged (STAGED_GENERATION_
    # STAGES.md#9: "needs no change here -- return frontend_ui's own
    # files unchanged rather than inventing one").
    "frontend_forms": {
        "frontend/src/App.js": (
            "import { fetchWorks } from './client';\n"
            "function App() { fetchWorks(); return <button onClick={fetchWorks}>retry loading empty error works</button>; }\n"
            "export default App;\n"
        ),
    },
    "frontend_tests_config": {
        "frontend/package.json": '{"name": "app"}\n',
        "frontend/tests/App.test.js": "test('x', () => {});\n",
    },
    "manifests": {
        "backend/requirements.txt": "flask\n",
        "config/README.md": "run instructions\n",
    },
}


def _happy_path_queues() -> dict[str, list[tuple[HonestState, str]]]:
    return {
        name: [(HonestState.PASS, _output(files))]
        for name, files in HAPPY_PATH_FILES.items()
    }


def test_all_eleven_stages_pass_and_are_written_to_the_real_workspace(
    tmp_path: pathlib.Path,
) -> None:
    workspace = _workspace(tmp_path)
    result = generate_staged_model_product(
        _blueprint(), _factory(_happy_path_queues()), workspace,
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11
    written = set(result.files)
    assert written == {
        path for files in HAPPY_PATH_FILES.values() for path in files
    }
    assert (workspace.root / "backend" / "schema.py").is_file()
    assert (workspace.root / "frontend" / "src" / "App.js").is_file()
    # backend_cors_boundary overwrote backend/main.py; the CORS-added
    # version, not backend_implementation's pre-CORS one, is what's on disk.
    assert "CORS(app)" in (workspace.root / "backend" / "main.py").read_text(encoding="utf-8")


def test_the_real_model_id_is_passed_to_every_stage_not_the_stage_name(
    tmp_path: pathlib.Path,
) -> None:
    models: dict[str, _QueueModel] = {}

    def factory(stage_name: str) -> tuple[_QueueModel, str]:
        if stage_name not in models:
            models[stage_name] = _QueueModel(_happy_path_queues()[stage_name])
        return models[stage_name], "qwen2.5-coder:14b"

    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    for stage_name, model in models.items():
        assert model.model_ids == ["qwen2.5-coder:14b"], (
            f"stage {stage_name!r} was called with model_ids {model.model_ids!r}, "
            "not the real model id"
        )


def test_a_stage_only_sees_its_declared_inputs_real_bytes(tmp_path: pathlib.Path) -> None:
    factory = _factory(_happy_path_queues())
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    # frontend_ui declares frontend_client, backend_contract and product_ux_spec as inputs.
    ui_prompt = factory.models["frontend_ui"].prompts[0]  # type: ignore[attr-defined]
    assert "fetchWorks" in ui_prompt  # frontend_client's real export, visible
    assert "title" in ui_prompt  # backend_contract's real declared field, visible
    assert "navigation_label" in ui_prompt  # product_ux_spec's real content, visible
    assert "list_works" not in ui_prompt  # backend_implementation's content, not declared


def test_manifests_stage_prompt_is_reduced_not_the_whole_candidate(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-046 (session evidence): sending every prior stage's full
    bytes to manifests caused a real HTTP-level timeout, 4/4 attempts."""
    factory = _factory(_happy_path_queues())
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    manifests_prompt = factory.models["manifests"].prompts[0]  # type: ignore[attr-defined]
    # None of the other 10 stages' real route/UI/test source bytes appear.
    assert "list_works" not in manifests_prompt
    assert "fetchWorks" not in manifests_prompt
    assert "test_placeholder" not in manifests_prompt
    # The mechanically-extracted signal (backend/requirements.txt's real
    # declared dependency) is still there, since manifests genuinely needs it.
    assert "flask" in manifests_prompt


def test_parse_stage_envelope_repairs_a_flat_ux_spec_response() -> None:
    flat_spec = json.loads(HAPPY_PATH_FILES["product_ux_spec"]["product/ux_spec.json"])
    envelope, failure = _parse_stage_envelope("product_ux_spec", json.dumps(flat_spec))
    assert failure is None
    assert envelope is not None
    assert {item.path: item.content for item in envelope.files} == {
        "product/ux_spec.json": json.dumps(flat_spec),
    }


def test_parse_stage_envelope_reports_the_original_error_when_no_repair_applies() -> None:
    """A real, unrelated contract violation at a different stage must
    surface its own real error, never a repair meant for a different
    stage's own known defect shape."""
    flat_spec = json.loads(HAPPY_PATH_FILES["product_ux_spec"]["product/ux_spec.json"])
    envelope, failure = _parse_stage_envelope("frontend_ui", json.dumps(flat_spec))
    assert envelope is None
    assert failure is not None and "violates the contract" in failure


def test_apply_deterministic_repairs_fixes_a_shadowed_route() -> None:
    """golden-work-096 (session evidence, frozen): a real qwen2.5-coder:14b
    reproduced this exact, already-clearly-explained route-shadowing
    defect unchanged across all 4 real frontend_forms attempts, exhausting
    the stage's full attempt budget -- proof the fix belonged to a
    deterministic repair. Proves the real sequencing function every stage
    attempt actually calls (`_apply_deterministic_repairs`, not just the
    standalone repair function in isolation) applies it."""
    stage_files = {
        "frontend/src/App.js": (
            "<Switch>"
            "<Route path='/works'><h2>Works</h2></Route>"
            "<Route path='/works/create'><h2>Create Work</h2></Route>"
            "</Switch>"
        ),
    }
    repaired = _apply_deterministic_repairs({}, stage_files)
    assert "<Route exact path='/works'>" in repaired["frontend/src/App.js"]
    assert "<Route path='/works/create'>" in repaired["frontend/src/App.js"]


def test_a_flat_ux_spec_response_is_deterministically_repaired(tmp_path: pathlib.Path) -> None:
    """golden-work-093/094 (session evidence, frozen, byte-identical
    failure reproduced on two independent real candidates): a real
    qwen2.5-coder:14b wrote this stage's own real, valid ux_spec content
    directly at the JSON top level instead of nesting it inside the
    generic `{"files": {...}}` stage envelope every stage's own prompt
    documents. Proves the real retry loop accepts it on the very first
    attempt via the deterministic repair (only one outcome is queued
    below -- a second attempt would raise IndexError), rather than
    retrying or ever surfacing ARK-ERR-0116."""
    queues = _happy_path_queues()
    flat_spec = json.loads(HAPPY_PATH_FILES["product_ux_spec"]["product/ux_spec.json"])
    queues["product_ux_spec"] = [(HonestState.PASS, json.dumps(flat_spec))]
    result = generate_staged_model_product(
        _blueprint(), _factory(queues), _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    assert "product/ux_spec.json" in result.files


def test_a_failing_attempt_is_retried_with_the_real_finding_as_feedback(
    tmp_path: pathlib.Path,
) -> None:
    queues = _happy_path_queues()
    bad = _output({"backend/main.py": "app = object()\n"})  # no route, no model
    good = queues["backend_contract"][0]
    queues["backend_contract"] = [(HonestState.PASS, bad), good]
    factory = _factory(queues)
    result = generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11
    prompts = factory.models["backend_contract"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    assert "backend_contract_no_routes" in prompts[1]


# -- FACTORY RELIABILITY CONVERGENCE: previous-attempt-output feedback ------
#
# Real, repository evidence: `goal-mtm6qrdr-apus8c` (backend_cors_boundary,
# a real repeated Python-syntax fingerprint) and `goal-mtolm3cv-ivuo9g`
# (product_ux_spec, a real repeated module-parity fingerprint) both hit
# ARK-ERR-0116 without the model ever seeing the exact bytes it wrote on
# the attempt that was rejected -- only a flat failure string naming a
# location/name in a file that had already been discarded. These tests
# regression-guard the fix generically, never by candidate id or domain.


def test_a_retried_stage_receives_its_own_previous_rejected_output(
    tmp_path: pathlib.Path,
) -> None:
    queues = _happy_path_queues()
    bad = _output({"backend/main.py": "app = object()\n"})
    good = queues["backend_contract"][0]
    queues["backend_contract"] = [(HonestState.PASS, bad), good]
    factory = _factory(queues)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    prompts = factory.models["backend_contract"].prompts  # type: ignore[attr-defined]
    first_payload = json.loads(prompts[0])
    second_payload = json.loads(prompts[1])
    assert "previous_attempt_output" not in first_payload
    assert second_payload["previous_attempt_output"] == {"backend/main.py": "app = object()\n"}


def test_previous_attempt_output_reflects_the_immediately_prior_attempt_not_the_first(
    tmp_path: pathlib.Path,
) -> None:
    """Two DIFFERENT real defects in a row (never the same fingerprint, so
    ARK-ERR-0116 correctly does not fire) -- the 3rd attempt's own prompt
    must show the 2nd attempt's own bytes, never the 1st's."""
    queues = _happy_path_queues()
    no_routes_or_models = _output({"backend/main.py": "app = object()  # first\n"})
    routes_but_no_models = _output({
        "backend/routes/task_routes.json": json.dumps(
            [{"path": "/works", "method": "GET", "model_fields": ["id"]}]
        ),
    })
    good = queues["backend_contract"][0]
    queues["backend_contract"] = [
        (HonestState.PASS, no_routes_or_models),
        (HonestState.PASS, routes_but_no_models),
        good,
    ]
    factory = _factory(queues)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    prompts = factory.models["backend_contract"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 3
    second_payload = json.loads(prompts[1])
    third_payload = json.loads(prompts[2])
    assert second_payload["previous_attempt_output"] == {
        "backend/main.py": "app = object()  # first\n"
    }
    assert "backend_contract_no_models" in third_payload["prior_attempt_failure"]
    assert "backend_contract_no_routes" not in third_payload["prior_attempt_failure"]
    assert third_payload["previous_attempt_output"] == {
        "backend/routes/task_routes.json": json.dumps(
            [{"path": "/works", "method": "GET", "model_fields": ["id"]}]
        ),
    }


def test_previous_attempt_output_is_absent_after_a_contract_violation(
    tmp_path: pathlib.Path,
) -> None:
    """A response that never even parses as a real `_StageEnvelope` leaves
    nothing real to show back -- `previous_attempt_files` must stay `None`,
    never the raw unparsed garbage passed off as real file content."""
    queues = _happy_path_queues()
    not_an_envelope = "not json at all"
    good = queues["backend_contract"][0]
    queues["backend_contract"] = [(HonestState.PASS, not_an_envelope), good]
    factory = _factory(queues)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    prompts = factory.models["backend_contract"].prompts  # type: ignore[attr-defined]
    second_payload = json.loads(prompts[1])
    assert "previous_attempt_output" not in second_payload
    assert "violates the contract" in second_payload["prior_attempt_failure"]


# -- F-0097 (BACKEND_CONTRACT_MULTI_MODEL_CONVERGENCE_GAP) ------------------
#
# Real, frozen repository evidence: `factory-goal-mtw5byq6-irjabg` wrote a
# real, otherwise-complete `backend/models.json` as a top-level JSON ARRAY
# of two individually valid `{table_name, fields}` objects and repeated the
# identical `backend_contract_no_models` fingerprint on both permitted
# attempts (ARK-ERR-0116). These tests regression-guard the fix generically
# -- never by candidate id -- and prove the validator's own acceptance
# boundary did not move.

#: The exact real shape `factory-goal-mtw5byq6-irjabg`'s own frozen artifact
#: (`sha256:6b3840a2...`) recorded for `backend/models.json`.
_F0097_ARRAY_MODELS_JSON = json.dumps([
    {
        "table_name": "maintenance_tasks",
        "fields": {
            "id": "integer", "task_name": "string",
            "description": "string", "status": "string",
        },
    },
    {
        "table_name": "service_providers",
        "fields": {
            "id": "integer", "provider_name": "string",
            "contact_info": "string", "service_type": "string",
        },
    },
])


def test_a_top_level_array_of_valid_models_still_fails_backend_contract() -> None:
    """A. The validator's own acceptance boundary must not move: two
    otherwise-complete model objects wrapped in a top-level array is still
    rejected."""
    findings = _backend_contract_findings({
        "backend/routes.json": json.dumps(
            [{"path": "/maintenance_tasks", "method": "GET"}]
        ),
        "backend/models.json": _F0097_ARRAY_MODELS_JSON,
    })
    codes = {f.code for f in findings}
    assert "backend_contract_no_models" in codes


def test_the_canonical_object_shape_still_passes_backend_contract() -> None:
    """B/G. The two already-canonical shapes -- one object per file, and
    one file nesting multiple models under their own keys -- both still
    pass, unchanged."""
    one_file_per_model = _backend_contract_findings({
        "backend/routes.json": json.dumps([{"path": "/works", "method": "GET"}]),
        "backend/models.json": json.dumps(
            {"table_name": "works", "fields": {"id": "integer"}}
        ),
    })
    assert not any(f.code == "backend_contract_no_models" for f in one_file_per_model)

    nested_multi_model = _backend_contract_findings({
        "backend/routes.json": json.dumps([{"path": "/works", "method": "GET"}]),
        "backend/models.json": json.dumps(
            {"fields": {"works": {"id": "integer"}, "tasks": {"id": "integer"}}}
        ),
    })
    assert not any(f.code == "backend_contract_no_models" for f in nested_multi_model)


def test_backend_contract_no_models_injects_the_structured_retry_hint(
    tmp_path: pathlib.Path,
) -> None:
    """C/D. `backend_contract` (stage 1, `Inputs: none`) has no real
    `mutation_contracts` -- before this fix, `repair_strategy`/`repair_hint`
    were nested entirely inside `if mutation_contracts:` and this stage
    could never receive either. The retry hint must now be present and
    must explicitly name the object-vs-array invariant, never the
    mutation-specific worked example (`useParams`) that would misdirect a
    stage this early in the pipeline."""
    queues = _happy_path_queues()
    good = queues["backend_contract"][0]
    bad = _output({
        "backend/routes.json": json.dumps(
            [{"path": "/maintenance_tasks", "method": "GET"}]
        ),
        "backend/models.json": _F0097_ARRAY_MODELS_JSON,
    })
    queues["backend_contract"] = [(HonestState.PASS, bad), good]
    factory = _factory(queues)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    prompts = factory.models["backend_contract"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2  # F. retry count/budget unchanged: one retry, as before
    second_payload = json.loads(prompts[1])
    assert second_payload["repair_strategy"] == "structured_hint"
    hint = second_payload["repair_hint"]
    assert "OBJECT" in hint and "ARRAY" in hint
    assert "backend_contract_no_models" in hint
    # Never the frontend-mutation worked example -- this stage has no
    # route/useParams concern of any kind.
    assert "useParams" not in hint
    assert "mutation_contracts" not in second_payload  # no frontend contract exists for this stage
    # E. previous-attempt output is still threaded back unchanged.
    assert second_payload["previous_attempt_output"] == {
        "backend/routes.json": json.dumps([{"path": "/maintenance_tasks", "method": "GET"}]),
        "backend/models.json": _F0097_ARRAY_MODELS_JSON,
    }


def test_stage_vocabulary_and_planner_shape_are_unchanged(tmp_path: pathlib.Path) -> None:
    """H. The F-0097 fix touches only stage 1's rule prose and prompt
    construction -- the planner's own stage graph (count, order, declared
    inputs) must be byte-identical to before."""
    vocabulary = StageVocabulary.load(REPO)
    stages = vocabulary.stages()
    assert len(stages) == 11
    backend_contract = next(s for s in stages if s.name == "backend_contract")
    assert backend_contract.inputs == ()
    assert backend_contract.order == 1


def test_f0097_historical_artifact_replay_no_normalization() -> None:
    """Historical replay of the real frozen F-0097 artifact
    (`sha256:6b3840a2...`, `factory-goal-mtw5byq6-irjabg`) through the
    fixed detection + hint path, with no model call. Proves: the array is
    still rejected, the failure maps to the new hint, the hint carries the
    exact corrective invariant, and the original bytes are never rewritten
    -- no normalization, no schema widening anywhere in this path."""
    files = {
        "backend/routes.json": json.dumps([
            {"path": "/maintenance_tasks", "method": "POST"},
            {"path": "/maintenance_tasks", "method": "GET"},
            {"path": "/maintenance_tasks/{id}", "method": "PUT"},
            {"path": "/maintenance_tasks/{id}", "method": "DELETE"},
            {"path": "/service_providers", "method": "POST"},
            {"path": "/service_providers", "method": "GET"},
            {"path": "/service_providers/{id}", "method": "PUT"},
            {"path": "/service_providers/{id}", "method": "DELETE"},
        ]),
        "backend/models.json": _F0097_ARRAY_MODELS_JSON,
    }
    findings = _backend_contract_findings(files)
    assert [f.code for f in findings] == ["backend_contract_no_models"]

    from arkali.engineering.factory.stage_prompting import _structured_hint_text

    prior_findings = tuple((f.code, f.path, f.detail) for f in findings)
    hint = _structured_hint_text([], prior_findings)
    assert "ONE JSON FILE PER MODEL" in hint
    assert "Never a top-level ARRAY" in hint
    # The original, real bytes are represented unchanged -- never rewritten,
    # split, or reinterpreted as a different shape anywhere in this path.
    assert files["backend/models.json"] == _F0097_ARRAY_MODELS_JSON
    parsed_back = json.loads(files["backend/models.json"])
    assert isinstance(parsed_back, list) and len(parsed_back) == 2


# -- F-0098 (BACKEND_CONTRACT_MULTI_MODEL_KEY_CONVENTION_GAP) ---------------
#
# Real, frozen repository evidence: `factory-goal-mtxqltea-oatre4` wrote a
# real, otherwise-complete `backend/models.json` as a top-level JSON OBJECT
# keyed directly by each model's own name (never F-0097's array) and
# repeated the identical `backend_contract_no_models` fingerprint on both
# permitted attempts. F-0097's own fix is confirmed still correct (the
# array remains rejected); this is a distinct real shape neither of the two
# pre-F-0098 canonical forms matched. The approved fix canonicalizes NEW
# generation on ONE FILE PER MODEL only; the historical single-file wrapper
# stays reader-supported for backward compatibility but is no longer
# prompted for.

#: The exact real shape `factory-goal-mtxqltea-oatre4`'s own frozen artifact
#: (`sha256:b9c721bf...`) recorded for `backend/models.json`.
_F0098_NAMED_OBJECT_MODELS_JSON = json.dumps({
    "members": {
        "table_name": "members",
        "fields": {
            "id": "INTEGER PRIMARY KEY", "name": "TEXT NOT NULL",
            "email": "TEXT NOT NULL", "membership_date": "DATE",
        },
    },
    "trainers": {
        "table_name": "trainers",
        "fields": {
            "id": "INTEGER PRIMARY KEY", "name": "TEXT NOT NULL",
            "email": "TEXT NOT NULL", "specialization": "TEXT",
        },
    },
})

#: The historical single-file wrapper form (golden-work-064) -- must
#: remain parseable/accepted for backward compatibility; never the new
#: prompted target.
_HISTORICAL_WRAPPER_MODELS_JSON = json.dumps({
    "fields": {
        "works": {"id": "integer"}, "tasks": {"id": "integer"},
    },
})


def test_a_named_top_level_object_still_fails_backend_contract() -> None:
    """D. The F-0098 shape -- a top-level object keyed directly by each
    model's own name -- is still rejected; the validator's own boundary
    did not move."""
    findings = _backend_contract_findings({
        "backend/routes.json": json.dumps([{"path": "/members", "method": "GET"}]),
        "backend/models.json": _F0098_NAMED_OBJECT_MODELS_JSON,
    })
    codes = {f.code for f in findings}
    assert "backend_contract_no_models" in codes


def test_one_file_per_model_canonical_shape_passes() -> None:
    """A/B. The new sole prompted target -- two models as two separate
    files, each its own canonical object -- passes with no finding."""
    findings = _backend_contract_findings({
        "backend/routes.json": json.dumps([{"path": "/members", "method": "GET"}]),
        "backend/models/members.json": json.dumps(
            {"table_name": "members", "fields": {"id": "integer"}}
        ),
        "backend/models/trainers.json": json.dumps(
            {"table_name": "trainers", "fields": {"id": "integer"}}
        ),
    })
    assert not any(f.code == "backend_contract_no_models" for f in findings)


def test_historical_wrapper_still_parses_for_backward_compatibility() -> None:
    """C. The pre-F-0098 wrapper shape must remain accepted -- reader
    behavior is unchanged, only the prompt-facing guidance moved."""
    findings = _backend_contract_findings({
        "backend/routes.json": json.dumps([{"path": "/works", "method": "GET"}]),
        "backend/models.json": _HISTORICAL_WRAPPER_MODELS_JSON,
    })
    assert not any(f.code == "backend_contract_no_models" for f in findings)

    from arkali.engineering.factory.product_ux_spec import _backend_declared_models

    names = _backend_declared_models({"backend/models.json": _HISTORICAL_WRAPPER_MODELS_JSON})
    assert names == {"works", "tasks"}


def test_backend_contract_no_models_hint_names_one_file_per_model_explicitly(
    tmp_path: pathlib.Path,
) -> None:
    """F/G/H/I/J. The retry hint for the F-0098 shape must explicitly say
    one-file-per-model, include a literal worked example, explicitly
    reject both known-bad shapes by name, still thread back the previous
    attempt's own bytes unchanged, and never touch the retry budget."""
    queues = _happy_path_queues()
    good = queues["backend_contract"][0]
    bad = _output({
        "backend/routes.json": json.dumps([{"path": "/members", "method": "GET"}]),
        "backend/models.json": _F0098_NAMED_OBJECT_MODELS_JSON,
    })
    queues["backend_contract"] = [(HonestState.PASS, bad), good]
    factory = _factory(queues)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    prompts = factory.models["backend_contract"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2  # J. retry budget unchanged
    second_payload = json.loads(prompts[1])
    assert second_payload["repair_strategy"] == "structured_hint"
    hint = second_payload["repair_hint"]
    assert "ONE JSON FILE PER MODEL" in hint  # F
    assert '{"table_name": "members", "fields": {...}}' in hint  # G: literal example
    assert "Never a top-level ARRAY" in hint  # H: rejects F-0097's shape by name
    assert '{"members": {...}, "trainers": {...}}' in hint  # H: rejects F-0098's shape by name
    assert "useParams" not in hint
    # I. previous-attempt output is still threaded back unchanged.
    assert second_payload["previous_attempt_output"] == {
        "backend/routes.json": json.dumps([{"path": "/members", "method": "GET"}]),
        "backend/models.json": _F0098_NAMED_OBJECT_MODELS_JSON,
    }


def test_f0098_historical_artifact_replay_no_normalization() -> None:
    """Historical replay of the real frozen F-0098 artifact
    (`sha256:b9c721bf...`, `factory-goal-mtxqltea-oatre4`) through the
    fixed detection + hint path, with no model call. Proves: the
    named-object shape is still rejected, the failure maps to the new
    hint, the hint's literal example makes the correction unambiguous, and
    the original bytes are never rewritten -- no normalization, no schema
    widening anywhere in this path."""
    files = {
        "backend/routes.json": json.dumps([
            {"path": "/members", "method": "GET"},
            {"path": "/members", "method": "POST"},
            {"path": "/members/{id}", "method": "GET"},
            {"path": "/members/{id}", "method": "PUT"},
            {"path": "/members/{id}", "method": "DELETE"},
            {"path": "/trainers", "method": "GET"},
        ]),
        "backend/models.json": _F0098_NAMED_OBJECT_MODELS_JSON,
    }
    findings = _backend_contract_findings(files)
    assert [f.code for f in findings] == ["backend_contract_no_models"]

    from arkali.engineering.factory.stage_prompting import _structured_hint_text

    prior_findings = tuple((f.code, f.path, f.detail) for f in findings)
    hint = _structured_hint_text([], prior_findings)
    assert "ONE JSON FILE PER MODEL" in hint
    assert '{"members": {...}, "trainers": {...}}' in hint
    # K / no normalization: the original, real bytes are represented
    # unchanged -- never rewritten, split, or reinterpreted.
    assert files["backend/models.json"] == _F0098_NAMED_OBJECT_MODELS_JSON
    parsed_back = json.loads(files["backend/models.json"])
    assert isinstance(parsed_back, dict) and set(parsed_back) == {"members", "trainers"}


def test_the_anti_loop_still_fires_when_previous_attempt_output_is_present(
    tmp_path: pathlib.Path,
) -> None:
    """Showing the model its own previous output must never weaken
    ARK-ERR-0116 -- two consecutive attempts producing the IDENTICAL real
    rejected content are still the same failure fingerprint and must still
    stop before the bounded budget is exhausted, exactly as before this fix."""
    queues = _happy_path_queues()
    always_same_bad = _output({"backend/main.py": "app = object()\n"})
    queues["backend_contract"] = [(HonestState.PASS, always_same_bad)] * 4
    factory = _factory(queues)
    with pytest.raises(ModelGenerationError) as excinfo:
        generate_staged_model_product(
            _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
        )
    assert "repeated the identical failure fingerprint" in str(excinfo.value)
    # Stopped after attempt 2, never reaching a 3rd or 4th real call.
    assert len(factory.models["backend_contract"].prompts) == 2  # type: ignore[attr-defined]


def test_a_syntax_error_retry_can_see_and_repair_the_previous_broken_line(
    tmp_path: pathlib.Path,
) -> None:
    """Real shape of `goal-mtm6qrdr-apus8c` (backend_cors_boundary): a
    location-anchored finding ("line N: ...") is useless on its own once
    the file it points into has been discarded. The retry prompt must now
    carry that exact file's own real bytes, so "line N" refers to
    something the model can actually see and edit."""
    queues = _happy_path_queues()
    broken = _output({
        "backend/main.py": (
            "from flask_cors import CORS\napp = object()\nCORS(app)\n"
            "x = ('CREATE TABLE works (\n  id INTEGER\n)')\n"
        ),
    })
    good = queues["backend_cors_boundary"][0]
    queues["backend_cors_boundary"] = [(HonestState.PASS, broken), good]
    factory = _factory(queues)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    prompts = factory.models["backend_cors_boundary"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    second_payload = json.loads(prompts[1])
    assert "python_syntax" in second_payload["prior_attempt_failure"]
    assert "CREATE TABLE works (" in second_payload["previous_attempt_output"]["backend/main.py"]
    assert "syntactically invalid" in second_payload["repair_hint"]
    assert "return the whole valid file" in second_payload["repair_hint"]


def test_a_module_parity_retry_can_see_the_previous_attempts_exact_invented_module(
    tmp_path: pathlib.Path,
) -> None:
    """Real shape of `goal-mtolm3cv-ivuo9g` (product_ux_spec): a
    name-anchored finding ("invented module ['book_id']") is now
    accompanied by the exact previous JSON the model itself wrote, not just
    the disclosed real/invented name pair inside a flat string."""
    queues = _happy_path_queues()
    good_spec = json.loads(HAPPY_PATH_FILES["product_ux_spec"]["product/ux_spec.json"])
    bad_spec = dict(good_spec)
    bad_spec["modules"] = [{**good_spec["modules"][0], "name": "book_id"}]
    bad = _output({"product/ux_spec.json": json.dumps(bad_spec)})
    good = queues["product_ux_spec"][0]
    queues["product_ux_spec"] = [(HonestState.PASS, bad), good]
    factory = _factory(queues)
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
    )
    prompts = factory.models["product_ux_spec"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    second_payload = json.loads(prompts[1])
    assert "ux_spec_invented_module" in second_payload["prior_attempt_failure"]
    assert "book_id" in second_payload["previous_attempt_output"]["product/ux_spec.json"]


def test_stage_budget_exhaustion_raises_and_writes_nothing_for_that_candidate(
    tmp_path: pathlib.Path,
) -> None:
    queues = _happy_path_queues()
    always_bad = _output({"backend/main.py": "app = object()\n"})
    queues["backend_contract"] = [(HonestState.PASS, always_bad)] * 4
    workspace = _workspace(tmp_path)
    with pytest.raises(ModelGenerationError):
        generate_staged_model_product(
            _blueprint(), _factory(queues), workspace,
            vocabulary=StageVocabulary.load(REPO),
        )
    assert not (workspace.root / "backend").exists()


@pytest.mark.parametrize("state", [HonestState.NOT_CONFIGURED, HonestState.PASS])
def test_empty_inference_is_terminal_without_content_retries(state: HonestState) -> None:
    declaration = StageVocabulary.load(REPO).stage("backend_contract")
    model = _QueueModel([(state, ""), (HonestState.PASS, _output(HAPPY_PATH_FILES["backend_contract"]))])
    with pytest.raises(ModelGenerationError) as excinfo:
        _generate_one_stage(
            declaration, _blueprint(), model, "test-model", {},
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS, max_attempts=4,
        )
    assert "infrastructure inference failure on attempt 1" in str(excinfo.value)
    assert len(model.prompts) == 1
    assert excinfo.value.last_raw_output == ""  # type: ignore[attr-defined]
    assert excinfo.value.last_completion_metadata is None  # type: ignore[attr-defined]


def test_non_pass_inference_is_terminal_even_with_partial_output() -> None:
    model = _QueueModel([(HonestState.NOT_CONFIGURED, "partial")])
    with pytest.raises(ModelGenerationError) as excinfo:
        _generate_one_stage(
            StageVocabulary.load(REPO).stage("backend_contract"), _blueprint(), model,
            "test-model", {}, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, max_attempts=4,
        )
    assert excinfo.value.last_raw_output == "partial"  # type: ignore[attr-defined]
    assert len(model.prompts) == 1


def test_budget_exhaustion_retains_the_last_raw_model_output(
    tmp_path: pathlib.Path,
) -> None:
    """A caller must be able to freeze real diagnostic evidence, not just a
    mechanical summary — golden-work-043 and this session's first
    golden-work-045 attempt both had to be reported without the model's
    actual rejected output because nothing retained it."""
    queues = _happy_path_queues()
    always_bad = _output({"backend/main.py": "app = object()\n"})
    queues["backend_contract"] = [(HonestState.PASS, always_bad)] * 4
    with pytest.raises(ModelGenerationError) as excinfo:
        generate_staged_model_product(
            _blueprint(), _factory(queues), _workspace(tmp_path),
            vocabulary=StageVocabulary.load(REPO),
        )
    assert excinfo.value.last_raw_output == always_bad  # type: ignore[attr-defined]


def test_unresolved_blueprint_refuses(tmp_path: pathlib.Path) -> None:
    unresolved = derive_blueprint("fast", AuthorityMap.load(REPO))
    assert not unresolved.is_fully_resolved
    with pytest.raises(ModelGenerationError):
        generate_staged_model_product(
            unresolved, _factory(_happy_path_queues()), _workspace(tmp_path),
            vocabulary=StageVocabulary.load(REPO),
        )


def test_out_of_range_per_stage_budget_refuses(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ModelGenerationError):
        generate_staged_model_product(
            _blueprint(), _factory(_happy_path_queues()), _workspace(tmp_path),
            vocabulary=StageVocabulary.load(REPO), per_stage_max_attempts=5,
        )


def test_backend_contract_findings_flags_missing_routes_and_models() -> None:
    findings = _backend_contract_findings({"backend/main.py": "app = object()\n"})
    codes = {f.code for f in findings}
    assert codes == {"backend_contract_no_routes", "backend_contract_no_models"}


def test_backend_contract_findings_passes_on_real_route_and_model() -> None:
    findings = _backend_contract_findings(HAPPY_PATH_FILES["backend_contract"])
    assert findings == []


# -- F-0079 (UPSTREAM_MODEL_NAME_FALLBACK_GAP) ------------------------------
#
# Real production evidence: goal-mtoun7ih-7odtyr's own real
# backend/models.json carried a real "fields" map with no "table_name" at
# all -- product_ux_spec's own reconciliation then fell back to the file's
# own generic stem ("models"), a plain English word with no domain content,
# which _resource_matching_name (F-0068's own fix) never normalizes (it
# only strips a trailing SINGULAR "model", and "models" ends in "s", not
# "model"). No later stage could ever satisfy that check without literally
# reproducing "models" as a user-facing module name. Caught here, at
# backend_contract itself -- the earliest point this is detectable, before
# any downstream stage ever sees the fallback name.


def test_backend_contract_findings_flags_a_model_with_no_table_name() -> None:
    findings = _backend_contract_findings({
        "backend/routes.json": json.dumps([{"path": "/x", "method": "GET"}]),
        "backend/models.json": json.dumps({"fields": {"id": "integer"}}),
    })
    codes = {f.code for f in findings}
    assert codes == {"backend_contract_model_missing_table_name"}


def test_backend_contract_findings_does_not_flag_an_empty_string_table_name() -> None:
    """A present but empty/whitespace `table_name` is not a real name either."""
    findings = _backend_contract_findings({
        "backend/routes.json": json.dumps([{"path": "/x", "method": "GET"}]),
        "backend/models.json": json.dumps({"table_name": "   ", "fields": {"id": "integer"}}),
    })
    assert any(f.code == "backend_contract_model_missing_table_name" for f in findings)


def test_backend_contract_findings_accepts_any_real_non_empty_table_name() -> None:
    """No hardcoded name list -- any real, non-empty string is accepted,
    including F-0068's own historical "task_model" shape (a real name, just
    an awkward one -- a separate, already-solved problem this check does
    not reopen or duplicate)."""
    for real_name in ("task_model", "works", "book_id", "x", "Anything_At_All"):
        findings = _backend_contract_findings({
            "backend/routes.json": json.dumps([{"path": "/x", "method": "GET"}]),
            "backend/models.json": json.dumps(
                {"table_name": real_name, "fields": {"id": "integer"}}
            ),
        })
        assert findings == [], real_name


def test_backend_contract_findings_flags_only_the_model_missing_a_table_name() -> None:
    """Multiple real models in the same real candidate -- only the one
    genuinely missing a table_name is named, never the other, and the path
    identifies exactly which file needs the fix."""
    findings = _backend_contract_findings({
        "backend/routes.json": json.dumps([{"path": "/x", "method": "GET"}]),
        "backend/students.json": json.dumps({"table_name": "students", "fields": {"id": "integer"}}),
        "backend/models.json": json.dumps({"fields": {"id": "integer"}}),
    })
    assert [f.path for f in findings] == ["backend/models.json"]


def test_a_real_missing_table_name_converges_on_retry_with_previous_attempt_output() -> None:
    """Unseen-domain proof (never "models"/"book_id"/library), exercising
    the real retry loop directly for just this one stage: backend_contract's
    own retry -- reusing F-0077's generic previous_attempt_output feedback,
    already wired for every stage -- converges on a real table_name once
    the defect is disclosed, exactly like any other backend_contract
    finding already does."""
    from arkali.engineering.factory.component_generation import _generate_one_stage

    missing_table_name = _output({
        "backend/routes/widget_routes.json": json.dumps(
            [{"path": "/widgets", "method": "GET", "model_fields": ["id"]}]
        ),
        "backend/widgets.json": json.dumps({"fields": {"id": {"type": "integer"}}}),
    })
    fixed_widgets = json.dumps(
        {"table_name": "widgets", "fields": {"id": {"type": "integer"}}}
    )
    fixed = _output({
        "backend/routes/widget_routes.json": json.dumps(
            [{"path": "/widgets", "method": "GET", "model_fields": ["id"]}]
        ),
        "backend/widgets.json": fixed_widgets,
    })
    model = _QueueModel([(HonestState.PASS, missing_table_name), (HonestState.PASS, fixed)])
    declaration = StageVocabulary.load(REPO).stage("backend_contract")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {},
        timeout_seconds=30.0, max_attempts=4,
    )
    assert len(model.prompts) == 2
    second_payload = json.loads(model.prompts[1])
    assert "backend_contract_model_missing_table_name" in second_payload["prior_attempt_failure"]
    assert second_payload["previous_attempt_output"] == {
        "backend/routes/widget_routes.json": json.dumps(
            [{"path": "/widgets", "method": "GET", "model_fields": ["id"]}]
        ),
        "backend/widgets.json": json.dumps({"fields": {"id": {"type": "integer"}}}),
    }
    assert stage_files["backend/widgets.json"] == fixed_widgets


def test_frontend_ui_findings_flags_unused_export_and_missing_states() -> None:
    files = {
        "frontend/src/client.js": "export function fetchWorks() { return fetch('/works'); }\n",
        "frontend/src/App.js": "function App() { return null; }\n",
    }
    findings = _frontend_ui_findings(files)
    codes = {f.code for f in findings}
    assert "frontend_ui_client_unused" in codes
    assert "frontend_ui_missing_state" in codes


def test_frontend_ui_findings_does_not_require_mutation_exports_to_be_called() -> None:
    """golden-work-082 (session evidence, frozen): fixing this check's own
    real export-extraction bug (ba46ff3) made it enforce STAGED_
    GENERATION_STAGES.md#8's literal wording ("the UI calls every
    function frontend_client exports") for the first time ever, and it
    immediately exhausted frontend_ui's full attempt budget on every
    declared create/update/delete export -- wiring those is
    frontend_forms's job (STAGES.md#9; this module's own
    `_frontend_ui_findings` docstring), and frontend_forms has not run
    yet at this point. A genuinely unused READ export must still be
    flagged in the same file."""
    files = {
        "frontend/src/client.js": (
            "async function fetchWorks() { return fetch('/works'); }\n"
            "async function fetchArchived() { return fetch('/archived'); }\n"
            "async function createWork(title) { return fetch('/works', {method: 'POST'}); }\n"
            "async function updateWork(id) { return fetch('/works/' + id, {method: 'PUT'}); }\n"
            "async function deleteWork(id) { return fetch('/works/' + id, {method: 'DELETE'}); }\n"
            "export { fetchWorks, fetchArchived, createWork, updateWork, deleteWork };\n"
        ),
        "frontend/src/App.js": (
            "import { fetchWorks } from './client';\n"
            "function App() { fetchWorks(); return 'loading empty error works'; }\n"
            "export default App;\n"
        ),
    }
    findings = _frontend_ui_findings(files)
    client_unused = next(f for f in findings if f.code == "frontend_ui_client_unused")
    assert "fetchArchived" in client_unused.detail
    for mutation_name in ("createWork", "updateWork", "deleteWork"):
        assert mutation_name not in client_unused.detail


def test_frontend_ui_findings_flags_a_missing_empty_state_specifically() -> None:
    """STAGED_GENERATION_STAGES.md#8 has always named "loading, empty and
    error states"; the check only ever compared against ("loading", "error")
    -- a real gap between the rule's own text and its check, not the rule,
    fixed alongside this session's wider UX-reconciliation work."""
    files = {
        "frontend/src/client.js": "export function fetchWorks() { return fetch('/works'); }\n",
        "frontend/src/App.js": (
            "function App() { fetchWorks(); return 'loading error'; }\nexport default App;\n"
        ),
    }
    findings = _frontend_ui_findings(files)
    state_findings = [f for f in findings if f.code == "frontend_ui_missing_state"]
    assert any("empty" in f.detail for f in state_findings)


def test_frontend_ui_findings_passes_on_real_wiring() -> None:
    files = {
        **HAPPY_PATH_FILES["frontend_client"],
        **HAPPY_PATH_FILES["frontend_ui"],
    }
    assert _frontend_ui_findings(files) == []


def test_frontend_ui_findings_requires_an_entry_point() -> None:
    """golden-work-061 (session evidence, frozen): manifests' own reduced
    context never sees the real component file name, so it cannot write
    a correct index.js — this must be required (and satisfiable) here,
    at the stage that actually knows what it just wrote."""
    files = {
        **HAPPY_PATH_FILES["frontend_client"],
        "frontend/src/App.js": HAPPY_PATH_FILES["frontend_ui"]["frontend/src/App.js"],
    }
    findings = _frontend_ui_findings(files)
    assert any(f.code == "missing_frontend_entry_point" for f in findings)


def test_backend_implementation_findings_catches_real_python_syntax_errors() -> None:
    """golden-work-045's real output (session evidence): an unterminated
    multi-line string inside a single-quoted CREATE TABLE call — passed
    every substring check that existed before this test."""
    broken = {
        "backend/app.py": (
            "app = object()\n"
            "@app.get('/works')\n"
            "def list_works():\n"
            "    x = ('CREATE TABLE works (\n"
            "      id INTEGER\n"
            "    )')\n"
        ),
    }
    findings = _backend_implementation_stage_findings(broken)
    assert [f.code for f in findings] == ["python_syntax"]


def test_backend_implementation_findings_does_not_require_cors() -> None:
    """CORS is backend_cors_boundary's job now, not backend_implementation's
    — real evidence (golden-work-045) showed the model reliably produces
    routes+schema+entrypoint together but did not reliably add CORS in the
    same bounded attempt even when this stage's rule explicitly required
    both; splitting the concern is the fix."""
    files = {**HAPPY_PATH_FILES["backend_schema"], **HAPPY_PATH_FILES["backend_implementation"]}
    assert _backend_implementation_stage_findings(files) == []


#: BACKEND_IMPLEMENTATION_LOCAL_FILE_COMPLETENESS_GAP (real evidence:
#: `factory-ea9cba11-89be-4b41-895f-5ea0069b495b`, live QWEN3.5/Bionic
#: run, session evidence, frozen). A real `qwen/qwen3.5-9b`'s own
#: `backend/app.py` imported and registered `members_bp`/`classes_bp`
#: from `backend.routes.members`/`backend.routes.classes`, but neither
#: referenced module was ever emitted, on all 4 real attempts --
#: `missing_api_routes` fired correctly, but had no structured retry hint
#: and `STAGED_GENERATION_STAGES.md#3` stated no same-response local-file
#: completeness invariant for backend Python imports (the exact invariant
#: `STAGED_GENERATION_STAGES.md#9` already states for frontend_forms).
_FROZEN_BACKEND_LOCAL_IMPORT_GAP_APP_PY = (
    "from flask import Flask\n"
    "from backend.routes.members import members_bp\n"
    "from backend.routes.classes import classes_bp\n\n"
    "app = Flask(__name__)\n\n"
    "app.register_blueprint(members_bp)\n"
    "app.register_blueprint(classes_bp)\n\n"
    "if __name__ == '__main__':\n"
    "    app.run(debug=True)\n"
)
_FROZEN_BACKEND_LOCAL_IMPORT_GAP_DB_PY = (
    "from backend.schema.init import init_db\n\n"
    "DB_PATH = \"data/gym.db\"\n\n"
    "init_db()\n\n"
    "import sqlite3\n\n"
    "def get_db_connection():\n"
    "    conn = sqlite3.connect(DB_PATH)\n"
    "    conn.row_factory = sqlite3.Row\n"
    "    return conn\n"
)


def test_a_frontend_forms_local_component_completeness_gap_also_exists_in_backend_implementation_frozen_replay() -> None:
    """Matrix item G: the real frozen `factory-ea9cba11-89be-4b41-895f-
    5ea0069b495b` attempt, replayed through the real, unmodified
    production checker -- app.py/db.py only, both referenced Blueprint
    modules absent -- still correctly produces `missing_api_routes`."""
    files = {
        "backend/app.py": _FROZEN_BACKEND_LOCAL_IMPORT_GAP_APP_PY,
        "backend/db.py": _FROZEN_BACKEND_LOCAL_IMPORT_GAP_DB_PY,
    }
    findings = _backend_implementation_stage_findings(files)
    assert any(f.code == "missing_api_routes" for f in findings)


def test_matrix_a_blueprint_import_with_module_absent_is_flagged() -> None:
    """Matrix item A."""
    files = {"backend/app.py": _FROZEN_BACKEND_LOCAL_IMPORT_GAP_APP_PY}
    findings = _backend_implementation_stage_findings(files)
    assert any(f.code == "missing_api_routes" for f in findings)


def test_matrix_b_blueprint_import_with_module_emitted_is_not_flagged_for_routes() -> None:
    """Matrix item B: once both referenced Blueprint files are genuinely
    emitted with real route decorators, `missing_api_routes` must not
    fire -- proving the route-detection fix (not only the prompt/hint
    additions) actually closes the gap."""
    files = {
        "backend/app.py": _FROZEN_BACKEND_LOCAL_IMPORT_GAP_APP_PY,
        "backend/db.py": _FROZEN_BACKEND_LOCAL_IMPORT_GAP_DB_PY,
        "backend/routes/members.py": (
            "from flask import Blueprint, jsonify\n"
            "members_bp = Blueprint('members', __name__)\n\n"
            "@members_bp.route('/members', methods=['GET'])\n"
            "def list_members():\n    return jsonify([])\n"
        ),
        "backend/routes/classes.py": (
            "from flask import Blueprint, jsonify\n"
            "classes_bp = Blueprint('classes', __name__)\n\n"
            "@classes_bp.route('/classes', methods=['GET'])\n"
            "def list_classes():\n    return jsonify([])\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert not any(f.code == "missing_api_routes" for f in findings)


def test_matrix_d_routes_implemented_inline_on_app_has_no_dangling_import_problem() -> None:
    """Matrix item D: the rule's own alternative repair choice (declare
    routes directly on the application instance instead of a separate
    module) must already pass cleanly, with no import to resolve at all."""
    files = {
        "backend/app.py": (
            "from flask import Flask, jsonify\n"
            "import sqlite3\n\n"
            "app = Flask(__name__)\n"
            "sqlite3.connect('data/gym.db').execute('CREATE TABLE IF NOT EXISTS members (id INTEGER)')\n\n"
            "@app.route('/members', methods=['GET'])\n"
            "def list_members():\n    return jsonify([])\n\n"
            "if __name__ == '__main__':\n    app.run(debug=True)\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert findings == []


def test_matrix_e_two_missing_route_modules_both_named_by_the_finding_path() -> None:
    """Matrix item E: the existing `missing_api_routes` finding is a
    single stage-level symptom (`path='backend/'`), not per-module -- both
    missing modules are captured by the one finding, and the structured
    hint (asserted separately below) names the general repair action
    rather than a per-file location, since no more precise existing
    finding exists for this (see DETECTION trace)."""
    files = {"backend/app.py": _FROZEN_BACKEND_LOCAL_IMPORT_GAP_APP_PY}
    findings = _backend_implementation_stage_findings(files)
    matches = [f for f in findings if f.code == "missing_api_routes"]
    assert len(matches) == 1
    assert matches[0].path == "backend/"


def test_matrix_f_unrelated_third_party_import_is_never_treated_as_a_missing_local_route_module() -> None:
    """Matrix item F: a real, resolvable third-party import (flask_cors)
    must never itself trigger `missing_api_routes` -- only the genuine
    absence of any resolvable route decorator does."""
    files = {
        "backend/app.py": (
            "from flask import Flask, jsonify\n"
            "from flask_cors import CORS\n\n"
            "app = Flask(__name__)\n"
            "CORS(app)\n\n"
            "@app.route('/members', methods=['GET'])\n"
            "def list_members():\n    return jsonify([])\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert not any(f.code == "missing_api_routes" for f in findings)


def test_missing_api_routes_has_an_actionable_structured_retry_hint() -> None:
    """RETRY_HINT_NONCONVERGENCE closes: `missing_api_routes` now has a
    real entry in `_SUPPORTED_HINT_INVARIANTS`, so a retry receives an
    explicit repair action (emit the referenced module, or inline the
    routes) instead of only the raw finding text."""
    from arkali.engineering.factory.stage_prompting import _structured_hint_text

    prior_findings = (
        ("missing_api_routes", "backend/", "backend source declares no HTTP API route"),
    )
    hint = _structured_hint_text([], prior_findings)
    assert "missing_api_routes" in hint
    assert "Blueprint" in hint or "local Python module" in hint
    assert "same response" in hint


def test_schema_bootstrap_reachability_recognizes_a_blueprint_file_as_route_declaring() -> None:
    """Matrix item K (existing backend checker non-regression, extended):
    `_schema_bootstrap_reachability_findings` must not wrongly demand an
    explicit import of the schema module from a file that itself declares
    real Blueprint routes -- the same route-decorator generalization
    `missing_api_routes` needed, reused rather than duplicated with a
    second, narrower fix."""
    from arkali.engineering.factory.product_preflight import inspect_product_files

    files = {
        "backend/schema/init.py": (
            "import sqlite3\n"
            "def init_db():\n"
            "    sqlite3.connect('data.db').execute('CREATE TABLE IF NOT EXISTS members (id INTEGER)')\n"
        ),
        "backend/routes/members.py": (
            "from flask import Blueprint, Flask, jsonify\n"
            "from backend.schema.init import init_db\n"
            "app = Flask(__name__)\n"
            "init_db()\n"
            "members_bp = Blueprint('members', __name__)\n\n"
            "@members_bp.route('/members', methods=['GET'])\n"
            "def list_members():\n    return jsonify([])\n\n"
            "app.register_blueprint(members_bp)\n"
            "if __name__ == '__main__':\n    app.run(debug=True)\n"
        ),
        "tests/backend/test_members.py": "def test_placeholder():\n    assert True\n",
        "frontend/src/App.js": "export default function App(){return null}\n",
        "frontend/public/index.html": '<div id="root"></div>\n',
        "frontend/package.json": '{"scripts":{"build":"echo ok"}}\n',
        "config/README.md": "run\n",
        "backend/requirements.txt": "flask\n",
    }
    report = inspect_product_files(files)
    assert "schema_bootstrap_unreachable" not in {item.code for item in report.findings}


#: SCHEMA_BOOTSTRAP_RETRY_HINT_GAP (real evidence: `factory-
#: catering-1790691970`, `schema_bootstrap_unreachable`, ARK-ERR-0116
#: exhausted, session evidence, frozen). `backend_schema`'s own real
#: `backend/db.py` created real schema; the real `backend/app.py` this
#: attempt wrote never imported it, instead redeclaring its own separate
#: `init_db`/connection logic from scratch -- the checker fired correctly,
#: but had no structured retry hint, confirmed by mechanically
#: reconstructing the real retry prompt this exact candidate would have
#: received (`repair_hint` was `None`).
_SCHEMA_BOOTSTRAP_GAP_DB_PY = (
    "import sqlite3\n"
    "def init_db():\n"
    "    conn = sqlite3.connect('app.db')\n"
    "    conn.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER)')\n"
    "    conn.commit()\n"
)


def test_matrix_a_separate_schema_module_imported_by_the_active_app_is_reachable() -> None:
    files = {
        "backend/db.py": _SCHEMA_BOOTSTRAP_GAP_DB_PY,
        "backend/app.py": (
            "from flask import Flask, jsonify\n"
            "from backend.db import init_db\n\n"
            "app = Flask(__name__)\n"
            "init_db()\n\n"
            "@app.route('/clients', methods=['GET'])\n"
            "def list_clients():\n    return jsonify([])\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert not any(f.code == "schema_bootstrap_unreachable" for f in findings)


def test_matrix_b_separate_schema_module_never_imported_is_unreachable() -> None:
    files = {
        "backend/db.py": _SCHEMA_BOOTSTRAP_GAP_DB_PY,
        "backend/app.py": (
            "from flask import Flask, jsonify\n\n"
            "app = Flask(__name__)\n\n"
            "@app.route('/clients', methods=['GET'])\n"
            "def list_clients():\n    return jsonify([])\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert any(f.code == "schema_bootstrap_unreachable" for f in findings)


def test_matrix_c_inline_schema_with_no_abandoned_second_implementation_passes() -> None:
    """A single, self-contained file that both creates schema and declares
    routes is trivially exempt -- its own schema creation always runs when
    it does (the checker's own documented rationale)."""
    files = {
        "backend/app.py": (
            "from flask import Flask, jsonify\n"
            "import sqlite3\n\n"
            "app = Flask(__name__)\n"
            "sqlite3.connect('app.db').execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER)')\n\n"
            "@app.route('/clients', methods=['GET'])\n"
            "def list_clients():\n    return jsonify([])\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert not any(f.code == "schema_bootstrap_unreachable" for f in findings)


def test_matrix_d_app_duplicates_bootstrap_logic_while_the_real_module_stays_unreachable() -> None:
    """The exact real frozen shape: app.py redeclares its own separate
    init_db/connection logic from scratch rather than importing the real,
    separate backend_schema-produced module -- the duplicate does not
    rescue the original module's own unreachable schema creation."""
    files = {
        "backend/db.py": _SCHEMA_BOOTSTRAP_GAP_DB_PY,
        "backend/app.py": (
            "from flask import Flask, jsonify\n"
            "import sqlite3\n\n"
            "app = Flask(__name__)\n\n"
            "def get_connection():\n    return sqlite3.connect('app.db')\n\n"
            "def init_db():\n"
            "    conn = get_connection()\n"
            "    conn.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER)')\n"
            "    conn.commit()\n\n"
            "init_db()\n\n"
            "@app.route('/clients', methods=['GET'])\n"
            "def list_clients():\n    return jsonify([])\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert any(f.code == "schema_bootstrap_unreachable" for f in findings)


def test_matrix_e_an_unrelated_import_does_not_satisfy_reachability() -> None:
    """Importing a different module that merely shares no real reference to
    the schema module's own name must not be mistaken for reachability."""
    files = {
        "backend/db.py": _SCHEMA_BOOTSTRAP_GAP_DB_PY,
        "backend/utils.py": "def helper():\n    return 1\n",
        "backend/app.py": (
            "from flask import Flask, jsonify\n"
            "from backend.utils import helper\n\n"
            "app = Flask(__name__)\n\n"
            "@app.route('/clients', methods=['GET'])\n"
            "def list_clients():\n    return jsonify([helper()])\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert any(f.code == "schema_bootstrap_unreachable" for f in findings)


def test_matrix_f_a_comment_or_string_literal_mentioning_the_module_does_not_satisfy_reachability() -> None:
    """`_module_referenced_on_an_import_line` only ever matches a real
    import/from line -- a comment or string literal naming the module was
    already, correctly, never enough before this fix, and stays that way;
    this change touches only the hint registry, never this detection."""
    files = {
        "backend/db.py": _SCHEMA_BOOTSTRAP_GAP_DB_PY,
        "backend/app.py": (
            "from flask import Flask, jsonify\n\n"
            "# TODO: wire up backend.db for schema bootstrap\n"
            "NOTE = 'see backend.db for schema'\n\n"
            "app = Flask(__name__)\n\n"
            "@app.route('/clients', methods=['GET'])\n"
            "def list_clients():\n    return jsonify([])\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert any(f.code == "schema_bootstrap_unreachable" for f in findings)


def test_matrix_g_schema_bootstrap_unreachable_has_an_actionable_structured_retry_hint() -> None:
    from arkali.engineering.factory.stage_prompting import _structured_hint_text

    prior_findings = (
        (
            "schema_bootstrap_unreachable", "backend/db.py",
            "'backend/db.py' creates real schema (CREATE TABLE / create_all) but no "
            "other real backend file ever imports it -- this schema-creation code can "
            "never actually run when the real application starts",
        ),
    )
    hint = _structured_hint_text([], prior_findings)
    assert "schema_bootstrap_unreachable" in hint
    assert "import and reuse" in hint
    assert "reachable" in hint


def test_matrix_h_an_unrelated_finding_code_never_receives_the_schema_bootstrap_invariant() -> None:
    from arkali.engineering.factory.stage_prompting import _structured_hint_text

    prior_findings = (
        ("missing_api_routes", "backend/", "backend source declares no HTTP API route"),
    )
    hint = _structured_hint_text([], prior_findings)
    assert "schema_bootstrap_unreachable" not in hint
    assert "import and reuse" not in hint


def _frozen_catering_blob():  # noqa: ANN202
    path = (
        REPO / "var" / "factory" / "evidence" / "blobs" / "sha256" / "cc"
        / "cc9ae4fbae8f4677b9a93a5aeb8e9dfc69822e221bbb35e84659af6e946e0aa5"
    )
    if not path.exists():
        pytest.skip("local frozen evidence not available")
    return json.loads(path.read_text(encoding="utf-8"))


def test_matrix_j_frozen_catering_replay_still_fails_the_checker() -> None:
    """Do NOT fix the model output -- the frozen invalid candidate must
    still fail exactly as it did live. If this ever passes, the hint
    registry change wrongly touched detection."""
    blob = _frozen_catering_blob()
    envelope, parse_failure = _parse_stage_envelope("backend_implementation", blob["last_raw_output"])
    assert parse_failure is None
    stage_files = {item.path: item.content for item in envelope.files}
    ws = REPO / "var/factory/candidates/factory-catering-1790691970"
    if not ws.exists():
        pytest.skip("local frozen candidate not available")
    visible_files = {
        p.relative_to(ws).as_posix(): p.read_text(encoding="utf-8")
        for p in ws.rglob("*") if p.is_file()
    }
    merged = {**visible_files, **stage_files}
    findings = _backend_implementation_stage_findings(merged)
    assert any(f.code == "schema_bootstrap_unreachable" for f in findings)


def test_matrix_k_frozen_catering_finding_now_maps_to_the_new_structured_hint() -> None:
    from arkali.engineering.factory.stage_prompting import _structured_hint_text

    blob = _frozen_catering_blob()
    prior_findings = (
        (
            "schema_bootstrap_unreachable", "backend/db.py",
            "'backend/db.py' creates real schema (CREATE TABLE / create_all) but no "
            "other real backend file ever imports it -- this schema-creation code can "
            "never actually run when the real application starts",
        ),
    )
    hint = _structured_hint_text([], prior_findings)
    assert "schema_bootstrap_unreachable" in hint
    assert blob["last_completion_metadata"]["finish_reason"] == "stop"


def test_matrix_i_the_real_reconstructed_retry_prompt_carries_the_new_hint() -> None:
    """Item I: use the real production `_stage_prompt` composition, not a
    reimplementation, to prove the actual retry this candidate would next
    receive now carries the structured invariant alongside the raw
    finding and the previous attempt's own real files."""
    from arkali.control.architecture.authority_map import AuthorityMap
    from arkali.control.specification.blueprint_engine import derive_blueprint
    from arkali.engineering.factory.generation_stages import StageVocabulary
    from arkali.engineering.factory.stage_prompting import _stage_prompt

    blob = _frozen_catering_blob()
    ws = REPO / "var/factory/candidates/factory-catering-1790691970"
    if not ws.exists():
        pytest.skip("local frozen candidate not available")
    visible_files = {
        p.relative_to(ws).as_posix(): p.read_text(encoding="utf-8")
        for p in ws.rglob("*") if p.is_file()
    }
    envelope, _ = _parse_stage_envelope("backend_implementation", blob["last_raw_output"])
    previous_attempt_files = {item.path: item.content for item in envelope.files}

    goal = (
        "1. The system must persist clients and events for a small event catering "
        "business using SQLite with at least 2 tables.\n"
        "2. The backend must expose at least 8 REST API endpoints supporting full "
        "create, read, update and delete operations for both clients and events.\n"
        "3. The frontend must allow creating, viewing, editing and deleting both "
        "clients and events within 2 screens.\n"
        "4. The backend must respond within 500 ms for a single record request "
        "under normal load."
    )
    blueprint = derive_blueprint(goal, AuthorityMap.load(REPO))
    declaration = StageVocabulary.load(REPO).stage("backend_implementation")
    finding_detail = (
        "'backend/db.py' creates real schema (CREATE TABLE / create_all) but no "
        "other real backend file ever imports it -- this schema-creation code can "
        "never actually run when the real application starts"
    )
    prior_findings = (("schema_bootstrap_unreachable", "backend/db.py", finding_detail),)
    prior_failure = f"schema_bootstrap_unreachable:backend/db.py:{finding_detail}"

    prompt = _stage_prompt(
        declaration, blueprint, visible_files, prior_failure, None,
        repair_strategy="structured_hint", prior_findings=prior_findings,
        previous_attempt_files=previous_attempt_files,
    )
    payload = json.loads(prompt)
    assert payload["prior_attempt_failure"] == prior_failure
    assert "backend/app.py" in payload["previous_attempt_output"]
    assert "backend/db.py" in payload["visible_prior_files"]
    assert payload.get("repair_hint") is not None
    assert "schema_bootstrap_unreachable" in payload["repair_hint"]


def test_matrix_l_missing_api_routes_hint_is_unaffected() -> None:
    from arkali.engineering.factory.stage_prompting import _structured_hint_text

    prior_findings = (
        ("missing_api_routes", "backend/", "backend source declares no HTTP API route"),
    )
    hint = _structured_hint_text([], prior_findings)
    assert "missing_api_routes" in hint
    assert "Blueprint" in hint or "local Python module" in hint


def test_matrix_m_frontend_hint_registry_is_unaffected() -> None:
    from arkali.engineering.factory.stage_prompting import _structured_hint_text

    prior_findings = (
        ("frontend_local_import_unresolved", "frontend/src/App.js", "imports './Thing' but no such file exists"),
    )
    hint = _structured_hint_text([], prior_findings)
    assert "frontend_local_import_unresolved" in hint
    assert "schema_bootstrap_unreachable" not in hint


def test_cors_boundary_findings_requires_cors() -> None:
    findings = _cors_boundary_stage_findings(HAPPY_PATH_FILES["backend_implementation"])
    assert any(f.code == "missing_browser_origin_boundary" for f in findings)


def test_cors_boundary_findings_passes_with_flask_cors() -> None:
    assert _cors_boundary_stage_findings(HAPPY_PATH_FILES["backend_cors_boundary"]) == []


def test_cors_boundary_findings_catches_real_python_syntax_errors() -> None:
    broken = {
        "backend/main.py": (
            "app = object()\n"
            "@app.get('/works')\n"
            "def list_works():\n"
            "    x = ('CREATE TABLE works (\n"
            "      id INTEGER\n"
            "    )')\n"
        ),
    }
    findings = _cors_boundary_stage_findings(broken)
    assert [f.code for f in findings] == ["python_syntax"]


def test_default_timeout_covers_default_output_budget_at_measured_floor() -> None:
    """`golden-work-075` and `golden-work-076` (real evidence, frozen): two
    fresh candidates with ordinary-sized prior-stage output both genuinely
    timed out at `frontend_ui`, identically, because the prior default
    timeout (300s) could not cover one full `DEFAULT_MAX_OUTPUT_TOKENS`
    generation at this real host's measured floor throughput (~7.1
    tokens/second, two independent live `/api/generate` calls). This does
    not re-measure that floor — it structurally refuses a future change
    that raises `DEFAULT_MAX_OUTPUT_TOKENS` or lowers
    `DEFAULT_TIMEOUT_SECONDS` without preserving the real margin that
    closed this defect."""
    measured_floor_tokens_per_second = 7.0
    worst_case_generation_seconds = DEFAULT_MAX_OUTPUT_TOKENS / measured_floor_tokens_per_second
    assert DEFAULT_TIMEOUT_SECONDS >= worst_case_generation_seconds * 1.5


class TestStageAwareTimeout:
    """`FRONTEND_FORMS_TIMEOUT_BUDGET_MISMATCH` (real evidence: `factory-
    goal-mu1chcxk-nlk6u7`). `DEFAULT_TIMEOUT_SECONDS` budgets only real,
    measured OUTPUT-token throughput and assumes every stage's own real
    prompt stays near the size the `frontend_ui`-stage calibration was
    built against. The real, measured `frontend_ui` prompt for this exact
    candidate was 13681 real characters; `frontend_forms`'s own real
    prompt for the identical candidate, one stage later with real prior
    frontend_ui output now also visible, was 20063 real characters (a
    real 1.47x ratio) -- and it genuinely timed out twice at the unscaled
    base budget, with a real, empty `last_raw_output` both times.
    `_REF_PROMPT_CHARS` is that real, measured `frontend_ui` figure,
    rounded up slightly so a normal-sized prompt stays at exactly the
    base timeout; `_MAX_TIMEOUT_SCALE` bounds the scale-up so a malformed
    or pathologically large prompt can never request an unbounded wait."""

    @staticmethod
    def _effective(prompt_chars: int) -> float:
        return DEFAULT_TIMEOUT_SECONDS * min(
            max(1.0, prompt_chars / _REF_PROMPT_CHARS), _MAX_TIMEOUT_SCALE)

    def test_a_burden_at_or_below_reference_stays_at_base(self) -> None:
        assert self._effective(1000) == DEFAULT_TIMEOUT_SECONDS
        assert self._effective(_REF_PROMPT_CHARS) == DEFAULT_TIMEOUT_SECONDS

    def test_b_burden_above_reference_scales_upward(self) -> None:
        scaled = self._effective(_REF_PROMPT_CHARS * 2)
        assert scaled == pytest.approx(DEFAULT_TIMEOUT_SECONDS * 2)
        assert scaled > DEFAULT_TIMEOUT_SECONDS

    def test_c_very_large_burden_stops_at_the_explicit_cap(self) -> None:
        assert self._effective(_REF_PROMPT_CHARS * 100) == pytest.approx(
            DEFAULT_TIMEOUT_SECONDS * _MAX_TIMEOUT_SCALE)

    def test_d_real_frontend_ui_burden_stays_near_base(self) -> None:
        """The real, measured `frontend_ui` prompt for `factory-goal-
        mu1chcxk-nlk6u7` (13681 chars) is at or below `_REF_PROMPT_CHARS`."""
        assert self._effective(13681) == DEFAULT_TIMEOUT_SECONDS

    def test_e_real_frontend_forms_burden_exceeds_878s(self) -> None:
        """The real, measured `frontend_forms` prompt for the identical
        candidate (20063 chars) that genuinely timed out at the old,
        unscaled base budget now receives a materially larger one."""
        assert self._effective(20063) > DEFAULT_TIMEOUT_SECONDS
        assert self._effective(20063) == pytest.approx(1257.83, abs=0.1)

    def test_f_base_timeout_is_never_reduced(self) -> None:
        for prompt_chars in (0, 1, 500, _REF_PROMPT_CHARS - 1, _REF_PROMPT_CHARS):
            assert self._effective(prompt_chars) == DEFAULT_TIMEOUT_SECONDS

    def test_g_formula_carries_no_stage_or_domain_hardcoding(self) -> None:
        """The formula is a pure function of character count alone --
        the same real prompt length yields the same effective timeout
        regardless of which stage produced it."""
        assert self._effective(20063) == self._effective(20063)

    def test_h_end_to_end_wiring_passes_the_computed_timeout(self) -> None:
        """Proves `_generate_one_stage` actually passes the computed,
        per-attempt effective timeout to `model.infer` -- not merely
        that the formula exists in isolation."""
        declaration = StageVocabulary.load(REPO).stage("backend_contract")
        big_visible = {"frontend/src/apiClient.js": "x" * (_REF_PROMPT_CHARS * 2)}
        model = _QueueModel([(HonestState.PASS, _output(HAPPY_PATH_FILES["backend_contract"]))])
        _generate_one_stage(
            declaration, _blueprint(), model, "test-model", big_visible,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS, max_attempts=1,
        )
        assert len(model.timeouts) == 1
        assert model.timeouts[0] > DEFAULT_TIMEOUT_SECONDS

    def test_i_retry_attempt_recomputes_from_the_larger_prompt(self) -> None:
        """Attempt 2's own prompt grows via `previous_attempt_files`;
        its own effective timeout must be recomputed, not reused from
        attempt 1, and may legitimately be larger."""
        declaration = StageVocabulary.load(REPO).stage("backend_contract")
        rejected = _output({"backend/models/widgets.json": "not json"})
        accepted = _output(HAPPY_PATH_FILES["backend_contract"])
        model = _QueueModel([(HonestState.PASS, rejected), (HonestState.PASS, accepted)])
        _generate_one_stage(
            declaration, _blueprint(), model, "test-model", {},
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS, max_attempts=2,
        )
        assert len(model.timeouts) == 2
        assert len(model.prompts[1]) > len(model.prompts[0])
        assert model.timeouts[1] >= model.timeouts[0]


# -- F-0080 (DOUBLE_SERIALIZATION_DEFECT) -----------------------------------
#
# Real production evidence: goal-mtow4gf9-84kplb's own real backend_cors_
# boundary attempt (recovered via F-0078's own new observability) shows a
# real qwen2.5-coder:14b double-escaping its own embedded newlines --
# writing a real, literal "\n" (backslash + n) where a single JSON escape
# was correct -- collapsing an entire real .py file onto one logical line
# and failing ast.parse with the exact historical "unexpected character
# after line continuation character" error goal-mtm6qrdr-apus8c also
# produced. The fix reuses model_product_generation._normalise_python_
# transport -- the one-shot path's own already-existing, already-correct
# primitive for this exact defect class -- wired into the staged retry
# loop for the first time, at the same point (materialization, right
# after parsing, before any check) the one-shot path already applies it.


def _double_escaped(real_content: str) -> str:
    """The exact real defect shape: every real newline replaced with a
    literal two-character backslash-n, mirroring goal-mtow4gf9-84kplb's
    own real raw provider output byte-for-byte."""
    return real_content.replace("\n", "\\n")


def test_a_double_escaped_python_stage_output_normalizes_and_passes_immediately(
    tmp_path: pathlib.Path,
) -> None:
    real_content = (
        "from flask_cors import CORS\n"
        "app = object()\n"
        "CORS(app)\n"
        "@app.get('/works')\n"
        "def list_works():\n"
        "    return []\n"
    )
    queues = _happy_path_queues()
    queues["backend_cors_boundary"] = [
        (HonestState.PASS, _output({"backend/main.py": _double_escaped(real_content)})),
    ]
    factory = _factory(queues)
    workspace = _workspace(tmp_path)
    result = generate_staged_model_product(
        _blueprint(), factory, workspace, vocabulary=StageVocabulary.load(REPO),
    )
    # Exactly one real attempt -- normalization ran before the checker, so
    # no retry was ever needed for a defect this generic already fixes.
    assert len(factory.models["backend_cors_boundary"].prompts) == 1  # type: ignore[attr-defined]
    assert workspace.root.joinpath("backend", "main.py").read_text(encoding="utf-8") == real_content
    assert result.attempts_used == 11


def test_a_legitimate_literal_backslash_n_in_otherwise_valid_python_is_preserved() -> None:
    """Case 2 (mandatory adversarial proof): a genuinely intended two-
    character backslash-n INSIDE a raw string, in a file that is otherwise
    completely valid Python (real newlines everywhere else), must survive
    byte-for-byte -- ast.parse already succeeds on the original, so
    _normalise_python_transport's own first check (`continue` on success)
    never touches it."""
    from arkali.engineering.factory.component_generation import _generate_one_stage

    real_content = (
        "import re\n"
        "from flask_cors import CORS\n"
        "app = object()\n"
        "CORS(app)\n"
        "PATTERN = re.compile(r'\\n')\n"  # a genuine, intentional literal \n
        "@app.get('/works')\n"
        "def list_works():\n"
        "    return []\n"
    )
    model = _QueueModel([(HonestState.PASS, _output({"backend/main.py": real_content}))])
    declaration = StageVocabulary.load(REPO).stage("backend_cors_boundary")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {}, timeout_seconds=30.0, max_attempts=4,
    )
    assert stage_files["backend/main.py"] == real_content


def test_a_still_broken_file_after_normalization_still_fails_the_real_checker(
    tmp_path: pathlib.Path,
) -> None:
    """Fails closed: a genuinely malformed file (a missing colon, unrelated
    to escaping) that ALSO happens to arrive double-escaped must still be
    rejected as real invalid syntax -- normalization must never silently
    paper over an unrelated real defect."""
    genuinely_broken = (
        "from flask_cors import CORS\n"
        "app = object()\n"
        "CORS(app)\n"
        "@app.get('/works')\n"
        "def list_works()\n"  # missing colon -- a real, unrelated syntax error
        "    return []\n"
    )
    queues = _happy_path_queues()
    always_broken = _output({"backend/main.py": _double_escaped(genuinely_broken)})
    queues["backend_cors_boundary"] = [(HonestState.PASS, always_broken)] * 4
    with pytest.raises(ModelGenerationError) as excinfo:
        generate_staged_model_product(
            _blueprint(), _factory(queues), _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
        )
    assert "python_syntax" in str(excinfo.value)


# -- F-0087 (REQUIREMENTS_TXT_ESCAPED_NEWLINE_NOT_WIRED_GAP) ---------------


def test_a_double_escaped_requirements_txt_normalizes_and_passes_immediately(
    tmp_path: pathlib.Path,
) -> None:
    """Real evidence: `factory-goal-mtqt1uk9-qfs6bw`. `_normalise_
    requirements` already existed (stdlib-package stripping) but was never
    wired into the staged-generation retry path at all -- only the one-shot
    `write_model_product_output`. A real `requirements.txt` with three
    genuinely declared packages collapsed onto one line by literal
    backslash-n sequences must now normalize and pass on the first real
    attempt, exactly as `_normalise_python_transport` already does for
    `.py` files."""
    real_content = "flask==2.3.2\nflask_cors>=3.0\npytest==7.4.0\nWerkzeug<3\n"
    escaped_content = "flask==2.3.2\\nflask_cors>=3.0\\npytest==7.4.0\nWerkzeug<3"
    queues = _happy_path_queues()
    queues["manifests"] = [
        (HonestState.PASS, _output({
            "backend/requirements.txt": escaped_content,
            "config/README.md": "run instructions\n",
        })),
    ]
    factory = _factory(queues)
    workspace = _workspace(tmp_path)
    result = generate_staged_model_product(
        _blueprint(), factory, workspace, vocabulary=StageVocabulary.load(REPO),
    )
    assert len(factory.models["manifests"].prompts) == 1  # type: ignore[attr-defined]
    assert workspace.root.joinpath("backend", "requirements.txt").read_text(
        encoding="utf-8",
    ) == real_content
    assert result.attempts_used == 11


def test_normalization_never_touches_a_non_python_file() -> None:
    """`_normalise_python_transport`'s own `.py`-only guard, proven at the
    staged-generation integration point: a JS file carrying the identical
    literal backslash-n shape is left completely alone. Exercises the one
    stage directly, avoiding unrelated downstream stages' own happy-path
    fixtures overwriting the same file."""
    from arkali.engineering.factory.component_generation import _generate_one_stage

    js_with_literal_backslash_n = "export function fetchWorks() { return 'a\\nb'; }\n"
    model = _QueueModel([(HonestState.PASS, _output({
        "frontend/src/client.js": js_with_literal_backslash_n,
    }))])
    declaration = StageVocabulary.load(REPO).stage("frontend_client")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {}, timeout_seconds=30.0, max_attempts=4,
    )
    assert stage_files["frontend/src/client.js"] == js_with_literal_backslash_n



# -- F-0090 (PACKAGE_JSON_ESCAPED_NEWLINE_NOT_NORMALIZED_GAP) --------------


def test_a_double_escaped_package_json_normalizes_and_passes_immediately(
    tmp_path: pathlib.Path,
) -> None:
    """Real evidence: `factory-goal-mtqz9w2b-cuqqqe`. A real, otherwise-
    correct `frontend/package.json` had every one of its own real
    newlines written as a literal `\\n` escape sequence -- invalid JSON
    that `npm install` failed outright on with `EJSONPARSE`, one step
    after this turn's own new read-only acceptance journey had already
    genuinely passed. `_normalise_json_transport` (mirroring `_normalise_
    python_transport`'s own parse-before/parse-after primitive exactly)
    must now normalize this on the first real attempt, no retry needed."""
    real_content = '{\n  "name": "app",\n  "scripts": {\n    "build": "vite build"\n  }\n}\n'
    escaped_content = (
        '{\\n  "name": "app",\\n  "scripts": {\\n    "build": '
        '"vite build"\\n  }\\n}\\n'
    )
    queues = _happy_path_queues()
    queues["frontend_tests_config"] = [
        (HonestState.PASS, _output({
            "frontend/package.json": escaped_content,
            "frontend/tests/App.test.js": "test('x', () => {});\n",
        })),
    ]
    factory = _factory(queues)
    workspace = _workspace(tmp_path)
    result = generate_staged_model_product(
        _blueprint(), factory, workspace, vocabulary=StageVocabulary.load(REPO),
    )
    assert len(factory.models["frontend_tests_config"].prompts) == 1  # type: ignore[attr-defined]
    written = workspace.root.joinpath("frontend", "package.json").read_text(encoding="utf-8")
    assert json.loads(written) == json.loads(real_content)
    assert result.attempts_used == 11


def test_json_normalization_never_touches_a_non_json_file() -> None:
    """`_normalise_json_transport`'s own `.json`-only guard, proven at the
    staged-generation integration point: a JS file carrying the identical
    literal backslash-n shape is left completely alone -- the exact
    counterpart to `test_normalization_never_touches_a_non_python_file`
    for the JSON side of this same fix."""
    from arkali.engineering.factory.component_generation import _generate_one_stage

    js_with_literal_backslash_n = "export function fetchWorks() { return 'a\\nb'; }\n"
    model = _QueueModel([(HonestState.PASS, _output({
        "frontend/src/client.js": js_with_literal_backslash_n,
    }))])
    declaration = StageVocabulary.load(REPO).stage("frontend_client")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {}, timeout_seconds=30.0, max_attempts=4,
    )
    assert stage_files["frontend/src/client.js"] == js_with_literal_backslash_n


def test_a_legitimate_escaped_newline_inside_valid_json_is_preserved() -> None:
    """Case 2 (mandatory adversarial proof) for JSON: a real, valid
    `package.json` whose `description` field legitimately contains an
    escaped `\\n` must survive byte-for-byte -- `json.loads` already
    succeeds on the original, so `_normalise_json_transport`'s own first
    check (`continue` on success) never touches it."""
    from arkali.engineering.factory.component_generation import _generate_one_stage

    real_content = json.dumps({"description": "line1\nline2", "scripts": {}})
    assert "\\n" in real_content  # sanity: a genuine, correctly-escaped newline
    model = _QueueModel([(HonestState.PASS, _output({
        "frontend/package.json": real_content,
        "frontend/tests/App.test.js": "test('x', () => {});\n",
    }))])
    declaration = StageVocabulary.load(REPO).stage("frontend_tests_config")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {}, timeout_seconds=30.0, max_attempts=4,
    )
    assert stage_files["frontend/package.json"] == real_content


def test_a_still_invalid_package_json_after_normalization_still_fails_the_real_checker(
    tmp_path: pathlib.Path,
) -> None:
    """Fails closed, the JSON counterpart to `test_a_still_broken_file_
    after_normalization_still_fails_the_real_checker`: genuinely invalid
    JSON (unrelated to escaping -- a trailing comma) that also happens to
    arrive double-escaped must still be rejected by the new
    `invalid_json_artifact` detection check, never silently waved
    through just because normalization ran."""
    genuinely_broken = '{\n  "name": "app",\n  "scripts": {},\n}\n'  # trailing comma
    queues = _happy_path_queues()
    always_broken = _output({
        "frontend/package.json": _double_escaped(genuinely_broken),
        "frontend/tests/App.test.js": "test('x', () => {});\n",
    })
    queues["frontend_tests_config"] = [(HonestState.PASS, always_broken)] * 4
    with pytest.raises(ModelGenerationError) as excinfo:
        generate_staged_model_product(
            _blueprint(), _factory(queues), _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
        )
    assert "invalid_json_artifact" in str(excinfo.value)


def test_a_domain_independent_double_escape_reproduces_the_same_fix() -> None:
    """Unseen-domain proof (never library/books, never the real Turkish
    goal's own vocabulary): the identical defect shape, in an unrelated
    inventory domain, converges via the identical, domain-agnostic fix.
    Exercises the one stage directly, matching the real evidence's own
    stage (backend_cors_boundary)."""
    from arkali.engineering.factory.component_generation import _generate_one_stage

    real_content = (
        "from flask_cors import CORS\n"
        "app = object()\n"
        "CORS(app)\n"
        "@app.get('/widgets')\n"
        "def list_widgets():\n"
        "    return []\n"
        "class WidgetRecord(object):\n"
        "    pass\n"
    )
    model = _QueueModel([(HonestState.PASS, _output({
        "backend/main.py": _double_escaped(real_content),
    }))])
    declaration = StageVocabulary.load(REPO).stage("backend_cors_boundary")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {},
        timeout_seconds=30.0, max_attempts=4,
    )
    assert stage_files["backend/main.py"] == real_content


def test_f0078_raw_evidence_stays_raw_while_the_written_file_is_normalized() -> None:
    """F-0078's own observability must keep freezing the REAL, original,
    un-normalized model text -- normalization is a materialization-layer
    concern, never something that hides what the provider actually said."""
    from arkali.engineering.factory.component_generation import _generate_one_stage
    from tests.engineering.test_stage_attempt_observability import _RecordingQueueModel

    real_content = (
        "from flask_cors import CORS\n"
        "app = object()\n"
        "CORS(app)\n"
        "@app.get('/works')\n"
        "def list_works():\n"
        "    return []\n"
    )
    double_escaped_output = _output({"backend/main.py": _double_escaped(real_content)})
    model = _RecordingQueueModel([(HonestState.PASS, double_escaped_output)])
    declaration = StageVocabulary.load(REPO).stage("backend_cors_boundary")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {}, timeout_seconds=30.0, max_attempts=4,
    )
    # The materialized, checked, workspace-bound content is normalized...
    assert stage_files["backend/main.py"] == real_content
    # ...but the frozen observability evidence still shows the REAL,
    # original, un-normalized bytes the provider actually returned.
    assert len(model.attempts) == 1
    recorded_raw_output = model.attempts[0][4]
    assert recorded_raw_output == double_escaped_output
    assert real_content not in recorded_raw_output


# -- F-0081 (STAGE_ENVELOPE_FLAT_MAP_GAP) -----------------------------------
#
# Real production evidence: goal-mtoxjx1x-cwtlad's own real frontend_client
# attempts 2-4 (recovered via F-0078's own observability) show the real
# model abandoning the correct {"files": [{"path", "content"}]} envelope
# after a real rejection and writing {"<path>": "<content>"} directly at
# the JSON top level -- the exact shape _StageEnvelope._normalise_path_map
# already accepts, unchanged, when explicitly passed as the "files" value;
# only the outer "files" key itself was ever missing. product_ux_spec's own
# historical flat-envelope defect (golden-work-093/094) recurring at a
# different, unrelated stage -- generalized here since every stage shares
# the identical file-map contract.


def test_a_flat_top_level_file_map_is_repaired_into_the_real_envelope() -> None:
    from arkali.engineering.factory.component_generation import _parse_stage_envelope

    raw = json.dumps({"frontend/src/widgetClient.js": "export function noop() {}\n"})
    envelope, failure = _parse_stage_envelope("frontend_client", raw)
    assert failure is None
    assert envelope is not None
    assert {f.path: f.content for f in envelope.files} == {
        "frontend/src/widgetClient.js": "export function noop() {}\n",
    }


def test_an_already_correct_envelope_is_never_touched_by_the_new_repair() -> None:
    from arkali.engineering.factory.component_generation import _parse_stage_envelope

    raw = json.dumps({"files": [{"path": "frontend/src/x.js", "content": "export {};\n"}]})
    envelope, failure = _parse_stage_envelope("frontend_client", raw)
    assert failure is None
    assert {f.path: f.content for f in envelope.files} == {"frontend/src/x.js": "export {};\n"}


def test_a_dict_shaped_files_value_is_still_handled_by_the_existing_validator() -> None:
    """The pre-existing `_normalise_path_map` path (`{"files": {path: content}}`)
    must keep working unchanged -- the new repair only ever applies when
    the "files" key is absent entirely, never as a second, competing path."""
    from arkali.engineering.factory.component_generation import _parse_stage_envelope

    raw = json.dumps({"files": {"frontend/src/y.js": "export {};\n"}})
    envelope, failure = _parse_stage_envelope("frontend_client", raw)
    assert failure is None
    assert {f.path: f.content for f in envelope.files} == {"frontend/src/y.js": "export {};\n"}


def test_a_non_string_value_fails_closed_never_guessed() -> None:
    """Ambiguous shape (Section 7): a value that is not itself a real file-
    content string must never be silently coerced -- fail closed."""
    from arkali.engineering.factory.component_generation import _repair_flat_file_envelope

    raw = json.dumps({"frontend/src/x.js": {"nested": "object"}})
    assert _repair_flat_file_envelope(raw) is None


def test_an_empty_object_fails_closed() -> None:
    from arkali.engineering.factory.component_generation import _repair_flat_file_envelope

    assert _repair_flat_file_envelope(json.dumps({})) is None


def test_malformed_json_fails_closed() -> None:
    from arkali.engineering.factory.component_generation import _repair_flat_file_envelope

    assert _repair_flat_file_envelope("{not json") is None


def test_a_top_level_list_is_not_treated_as_a_flat_file_map() -> None:
    from arkali.engineering.factory.component_generation import _repair_flat_file_envelope

    assert _repair_flat_file_envelope(json.dumps(["frontend/src/x.js"])) is None


def test_f0078_raw_evidence_stays_raw_across_the_new_flat_map_repair() -> None:
    """The frozen observability evidence must still show the real, original,
    un-repaired flat JSON the provider actually returned -- repair is a
    parsing-layer concern, not something that rewrites what was observed."""
    from arkali.engineering.factory.component_generation import _generate_one_stage
    from tests.engineering.test_stage_attempt_observability import _RecordingQueueModel

    flat_output = _output_flat({"frontend/src/apiClient.js": "export function noop() {}\n"})
    model = _RecordingQueueModel([(HonestState.PASS, flat_output)])
    declaration = StageVocabulary.load(REPO).stage("frontend_client")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {}, timeout_seconds=30.0, max_attempts=4,
    )
    assert stage_files["frontend/src/apiClient.js"] == "export function noop() {}\n"
    assert len(model.attempts) == 1
    assert model.attempts[0][4] == flat_output  # raw_output, byte-for-byte as returned


def test_the_real_historical_frontend_client_attempts_now_reconstruct_correctly() -> None:
    """Direct replay of goal-mtoxjx1x-cwtlad's own real, frozen attempt
    bytes (F-0078 evidence) through the fixed parser: attempt 1's already-
    correct envelope is unaffected; attempts 2-4's real flat envelopes,
    previously rejected purely on shape, now parse and reach the real
    checker, which correctly still rejects the still-invalid JS in
    attempts 1-2 and correctly accepts the real, valid axios-based JS in
    attempt 3 -- proving the fix changes envelope recognition only, never
    checker strictness."""
    from arkali.engineering.factory.component_generation import _parse_stage_envelope
    from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings

    attempt_1_raw = json.dumps({"files": [{
        "path": "frontend/src/apiClient.js",
        "content": '{\n  "getOverdueBooks": "GET /api/books/overdue"\n}',
    }]})
    attempt_2_raw = json.dumps({
        "frontend/src/apiClient.js": (
            "{\n  \"getOverdueBooks\": function() {\n    return fetch('/api/books/overdue', {\n"
            "      method: 'GET'\n    }).then(response => response.json());\n  }\n}"
        ),
    })
    attempt_3_raw = json.dumps({
        "frontend/src/apiClient.js": (
            "const axios = require('axios');\n\nasync function getOverdueBooks() {\n"
            "  const response = await axios.get('/api/books/overdue');\n  return response.data;\n"
            "}\n\nmodule.exports = {\n  getOverdueBooks\n};"
        ),
    })

    for label, raw, expect_pass in (
        ("attempt 1", attempt_1_raw, False),
        ("attempt 2", attempt_2_raw, False),
        ("attempt 3", attempt_3_raw, True),
    ):
        envelope, failure = _parse_stage_envelope("frontend_client", raw)
        assert failure is None, f"{label}: envelope should now parse, got {failure!r}"
        files = {f.path: f.content for f in envelope.files}
        findings = frontend_contract_findings(files)
        assert (not findings) == expect_pass, f"{label}: findings={findings}"


# -- F-0086 (FRONTEND_CLIENT_PATH_PREFIX_VACUITY_GAP) -----------------------


def test_frontend_client_rejects_real_files_missing_the_frontend_src_prefix() -> None:
    """Real evidence: `factory-goal-mtqrbyqj-5m1bf8`. The model's own real
    output for this stage used bare `src/...` paths (the exact convention
    its own immediately preceding stage had already, silently, gotten away
    with) instead of `frontend/src/...`. Every check in `frontend_contract_
    findings` filters by that exact prefix, so a real attempt using ANY
    other path silently produced an EMPTY frontend blob -- no syntax
    findings (nothing to parse), no CORS finding (an empty string never
    contains "http://localhost:"), and no contract-drift finding either
    for this real, GET-only backend (that loop's own `_exposes` check
    never runs for a method the backend never exposes) -- passing
    vacuously on content that was never actually inspected at all,
    exactly the class of gap `_backend_tests_stage_findings`'s own
    `backend_tests_missing_top_level_path` (golden-work-048) already
    closed for `tests/`."""
    from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings

    files = {
        "src/apiClient.js": (
            "import axios from 'axios';\nconst apiClient = { "
            "getOverdueBooks: async () => (await axios.get('/api/books/overdue')).data };\n"
            "export default apiClient;"
        ),
        "src/App.js": "export default function App() { return null; }\n",
    }
    findings = frontend_contract_findings(files)
    assert [f.code for f in findings] == ["frontend_client_missing_top_level_path"]


def test_frontend_client_is_silent_once_files_carry_the_real_prefix() -> None:
    from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings

    files = {
        "frontend/src/apiClient.js": (
            "import axios from 'axios';\nconst apiClient = { "
            "getOverdueBooks: async () => (await axios.get('/api/books/overdue')).data };\n"
            "export default apiClient;"
        ),
    }
    assert frontend_contract_findings(files) == []


def test_frontend_client_rejects_fetch_that_parses_non_success_as_domain_data() -> None:
    from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings

    files = {
        "frontend/src/apiClient.js": (
            "export async function fetchWidgets() {\n"
            "  const response = await fetch('http://localhost:5000/widgets');\n"
            "  return response.json();\n"
            "}\n"
        ),
    }
    findings = frontend_contract_findings(files)
    assert any(f.code == "frontend_client_missing_http_failure_branch" for f in findings)


def test_frontend_client_accepts_fetch_with_a_real_status_failure_branch() -> None:
    from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings

    files = {
        "frontend/src/apiClient.js": (
            "export async function fetchWidgets() {\n"
            "  const response = await fetch('/widgets');\n"
            "  if (!response.ok) throw new Error(`HTTP ${response.status}`);\n"
            "  return response.json();\n"
            "}\n"
        ),
    }
    assert frontend_contract_findings(files) == []


def test_frontend_client_does_not_false_positive_axios_default_failure_semantics() -> None:
    from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings

    files = {
        "frontend/src/apiClient.js": (
            "import axios from 'axios';\n"
            "export async function fetchWidgets() { return (await axios.get('/widgets')).data; }\n"
        ),
    }
    assert frontend_contract_findings(files) == []


def test_frontend_client_rejects_unsafe_fetch_then_json_chain() -> None:
    from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings

    files = {
        "frontend/src/apiClient.js": (
            "export function fetchWidgets() {\n"
            "  return fetch('/widgets').then(response => response.json());\n"
            "}\n"
        ),
    }
    findings = frontend_contract_findings(files)
    assert any(f.code == "frontend_client_missing_http_failure_branch" for f in findings)


def test_frontend_client_accepts_failure_aware_fetch_then_chain() -> None:
    from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings

    files = {
        "frontend/src/apiClient.js": (
            "export function fetchWidgets() {\n"
            "  return fetch('/widgets').then(response => {\n"
            "    if (!response.ok) throw new Error('request failed');\n"
            "    return response.json();\n"
            "  });\n"
            "}\n"
        ),
    }
    assert frontend_contract_findings(files) == []


def _output_flat(files: dict[str, str]) -> str:
    return json.dumps(files)


# -- F-0082 (OBJECT_LITERAL_AT_STATEMENT_POSITION_GAP) ----------------------


def test_the_enriched_semantic_finding_reaches_the_real_retry_context() -> None:
    """End-to-end proof that the sharper diagnosis
    (javascript_syntax_preflight._is_object_literal_at_statement_position)
    actually reaches attempt 2's own real prompt through the existing,
    unmodified F-0077 mechanism -- zero new wiring needed anywhere in the
    retry loop itself."""
    from arkali.engineering.factory.component_generation import _generate_one_stage

    bad = _output({
        "frontend/src/apiClient.js": '{\n  "getOverdueBooks": "GET /api/books/overdue"\n}',
    })
    good = _output({
        "frontend/src/apiClient.js": (
                "export async function getOverdueBooks() {\n"
                "  const response = await fetch('/api/books/overdue');\n"
                "  if (!response.ok) throw new Error(`HTTP ${response.status}`);\n"
                "  return response.json();\n}\n"
        ),
    })
    model = _QueueModel([(HonestState.PASS, bad), (HonestState.PASS, good)])
    declaration = StageVocabulary.load(REPO).stage("frontend_client")
    stage_files = _generate_one_stage(
        declaration, _blueprint(), model, "test-model", {}, timeout_seconds=30.0, max_attempts=4,
    )
    assert len(model.prompts) == 2
    second_payload = json.loads(model.prompts[1])
    assert "object literal" in second_payload["prior_attempt_failure"]
    assert "frontend/src/apiClient.js" in stage_files


# -- F-0100 PATH A (BACKEND_SCHEMA_TRUNCATED_GENERATION_GAP), preventive
# generation-rule strengthening -----------------------------------------
#
# Real, frozen evidence: `factory-goal-mtyeas61-75cn2k`'s own historical
# failure, and three further bounded live reproductions (P1/P2/P3, all
# syntax-valid but all using the identical anti-pattern), showed
# `backend_schema` systematically re-reading backend_contract's own JSON
# files at RUNTIME (`json.load`) and dynamically synthesizing `CREATE
# TABLE` text through nested f-string/dict-access composition, rather
# than the direct/literal emission the stage's own pre-existing rule
# already intends. `STAGED_GENERATION_STAGES.md#2` now names this
# anti-pattern explicitly. This is a generation-instruction change only:
# the checker (`_schema_only_findings`) and retry mechanism are
# byte-unchanged, proven below by continuing to accept the exact real
# P1/P2/P3 output.

#: The exact real content all three bounded live reproductions produced
#: (`sha256:142caca2b0...`), byte-identical across P1/P2/P3 -- syntax
#: valid, but exhibiting every element the new rule text now names:
#: runtime `json.load`, dynamic dict traversal via `.items()`, and
#: f-string-synthesized `CREATE TABLE` text.
_F0100_DYNAMIC_DERIVATION_DB_PY = (
    "import sqlite3\nimport json\n\n"
    "with open('backend/models/equipment.json', 'r') as f:\n"
    "    equipment_schema = json.load(f)\n\n"
    "with open('backend/models/rentals.json', 'r') as f:\n"
    "    rentals_schema = json.load(f)\n\n"
    "conn = sqlite3.connect('tool_rental.db')\n"
    "cursor = conn.cursor()\n\n"
    "create_equipment_table = f\"CREATE TABLE IF NOT EXISTS "
    "{equipment_schema['table_name']} (\"\n"
    "create_equipment_table += ', '.join([f\"{field} {field_type}\" "
    "for field, field_type in equipment_schema['fields'].items()])\n"
    "create_equipment_table += \")\"\n"
    "cursor.execute(create_equipment_table)\n\n"
    "conn.commit()\nconn.close()\n"
)


class TestF0100BackendSchemaPreventiveRule:
    """A. direct/literal schema construction is required. B.
    backend_contract is named as the generation-time source of schema
    truth. C/D/E. runtime `json.load` re-derivation, dynamic field
    traversal and nested f-string SQL synthesis are each named and
    discouraged. F. table/column identifiers are required to be emitted
    directly."""

    @staticmethod
    def _rule() -> str:
        return StageVocabulary.load(REPO).stage("backend_schema").rule

    def test_a_direct_literal_construction_is_required(self) -> None:
        rule = self._rule()
        assert "DIRECT" in rule and "LITERAL" in rule

    def test_b_backend_contract_named_as_the_source_of_truth(self) -> None:
        rule = self._rule()
        assert "backend_contract's own JSON files already state" in rule
        assert "directly out of your own visible context" in rule

    def test_c_runtime_json_load_rederivation_is_discouraged(self) -> None:
        rule = self._rule()
        assert "reopens or `json.load`s backend_contract's own JSON" in rule
        assert "application runtime" in rule

    def test_d_dynamic_field_traversal_is_discouraged(self) -> None:
        rule = self._rule()
        assert "dynamically traverses a runtime-loaded model dict" in rule

    def test_e_nested_f_string_sql_synthesis_is_discouraged(self) -> None:
        rule = self._rule()
        assert "nested f-string or dict-access composition" in rule
        assert "CREATE TABLE" in rule

    def test_f_identifiers_must_be_emitted_directly(self) -> None:
        rule = self._rule()
        assert "written out by its own real name" in rule

    def test_g_the_existing_literal_happy_path_fixture_still_passes(self) -> None:
        """Item G: the current expected `backend_schema` output contract
        is unchanged -- the pre-existing literal fixture every other test
        already relies on still produces zero findings."""
        findings = _schema_only_findings(HAPPY_PATH_FILES["backend_schema"])
        assert findings == []

    def test_h_the_checker_still_accepts_valid_dynamic_derivation_output(self) -> None:
        """This is a generation-INSTRUCTION change, never a new runtime
        checker: the real P1/P2/P3 output is syntactically complete and
        must continue to pass exactly as it did live -- prevention is
        pursued at the prompt/rule level, not by rejecting valid Python
        the model might still produce despite the new instruction."""
        files = {"backend/db.py": _F0100_DYNAMIC_DERIVATION_DB_PY}
        assert _schema_only_findings(files) == []

    def test_i_stage_vocabulary_and_retry_budget_are_unchanged(self) -> None:
        """H/I: the planner's own stage graph and the real bounded-attempt
        ceiling are untouched by a prose-only rule change."""
        stages = StageVocabulary.load(REPO).stages()
        assert len(stages) == 11
        decl = next(s for s in stages if s.name == "backend_schema")
        assert decl.order == 2
        assert decl.inputs == ("backend_contract",)
        assert MAX_STAGE_ATTEMPTS == 4

    def test_j_python_syntax_structured_hint_is_generic(self) -> None:
        from arkali.engineering.factory.stage_prompting import _SUPPORTED_HINT_INVARIANTS

        hint = _SUPPORTED_HINT_INVARIANTS["python_syntax"]
        assert "parser-reported location" in hint
        assert "whole valid file" in hint

    def test_historical_replay_the_real_anti_pattern_is_named_by_every_element(self) -> None:
        """Section 11: without a model call, prove the new rule text would
        explicitly discourage the exact real historical/P1-P3 construct --
        every element the fixture actually exhibits (runtime `json.load`,
        `.items()`-driven dynamic traversal, an f-string building `CREATE
        TABLE` text) is named in the rule as something never to do, and
        the fixture itself is never patched, normalized or rewritten."""
        rule = self._rule()
        fixture = _F0100_DYNAMIC_DERIVATION_DB_PY
        assert "json.load(f)" in fixture and "json.load" in rule
        assert ".items()" in fixture and "traverses a runtime-loaded model dict" in rule
        assert 'f"CREATE TABLE' in fixture and "CREATE TABLE" in rule
        # The fixture's own real bytes are never rewritten by this test.
        assert fixture.count("json.load(f)") == 2

    def test_no_golden_domain_token_leaked_into_the_new_rule_text(self) -> None:
        rule = self._rule()
        banned = ("student", "payment", "course", "task", "/tasks", "/students")
        lowered = rule.lower()
        for token in banned:
            assert token not in lowered, token


#: BACKEND_SCHEMA_EXECUTABLE_PERSISTENCE_CONTRACT (real evidence:
#: `factory-tutoring-1790697700`, `missing_persistence_code` x2,
#: ARK-ERR-0116 exhausted, session evidence, frozen). The real, only
#: output this attempt wrote for `backend_schema`.
_FROZEN_TUTORING_SCHEMA_SQL_ONLY = {
    "backend/db/schema.sql": (
        "-- SQLite Schema for Tutoring Service\n"
        "CREATE TABLE IF NOT EXISTS tutors (\n"
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "    name TEXT NOT NULL\n"
        ");\n\n"
        "CREATE TABLE IF NOT EXISTS sessions (\n"
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "    tutor_id INTEGER NOT NULL,\n"
        "    FOREIGN KEY (tutor_id) REFERENCES tutors(id)\n"
        ");\n"
    ),
}


class TestBackendSchemaExecutablePersistenceContract:
    """A-N: `backend_schema` must emit real, executable Python persistence
    -- a standalone `.sql`/migration/DDL-only artifact never satisfies
    this rule by itself, no matter how valid its own SQL is."""

    @staticmethod
    def _rule() -> str:
        return StageVocabulary.load(REPO).stage("backend_schema").rule

    def test_a_schema_sql_only_output_is_rejected(self) -> None:
        findings = _schema_only_findings(_FROZEN_TUTORING_SCHEMA_SQL_ONLY)
        assert any(f.code == "missing_persistence_code" for f in findings)

    def test_b_migration_sql_only_output_is_rejected(self) -> None:
        files = {"backend/migrations/0001_initial.sql": "CREATE TABLE tutors (id INTEGER);\n"}
        findings = _schema_only_findings(files)
        assert any(f.code == "missing_persistence_code" for f in findings)

    def test_c_executable_python_sqlite_persistence_passes(self) -> None:
        files = {
            "backend/db.py": (
                "import sqlite3\n"
                "def init_db():\n"
                "    conn = sqlite3.connect('app.db')\n"
                "    conn.execute('CREATE TABLE IF NOT EXISTS tutors (id INTEGER)')\n"
                "    conn.commit()\n"
            ),
        }
        assert _schema_only_findings(files) == []

    def test_d_python_file_with_only_inert_sql_text_and_no_sqlite_usage_still_fails(self) -> None:
        """A `.py` file that merely holds SQL as a string constant, with no
        real `sqlite3`/`sqlite://` usage anywhere, must not be mistaken for
        executable persistence -- the checker's own existing `uses_sqlite`
        gate already requires a real connection marker, unchanged by this
        fix."""
        files = {
            "backend/schema_text.py": (
                "SCHEMA = \"CREATE TABLE tutors (id INTEGER)\"\n"
            ),
        }
        findings = _schema_only_findings(files)
        assert any(f.code == "missing_persistence_code" for f in findings)

    def test_e_python_persistence_with_an_optional_accompanying_sql_artifact_passes(self) -> None:
        files = {
            **_FROZEN_TUTORING_SCHEMA_SQL_ONLY,
            "backend/db.py": (
                "import sqlite3\n"
                "def init_db():\n"
                "    conn = sqlite3.connect('app.db')\n"
                "    conn.execute('CREATE TABLE IF NOT EXISTS tutors (id INTEGER)')\n"
                "    conn.commit()\n"
            ),
        }
        assert _schema_only_findings(files) == []

    def test_f_valid_python_persistence_using_create_table_passes(self) -> None:
        assert _schema_only_findings(HAPPY_PATH_FILES["backend_schema"]) == []

    def test_g_frozen_tutoring_evidence_still_fails_before_and_after_the_fix(self) -> None:
        """The frozen INVALID output must still fail -- this fix changes
        retry guidance only, never detection."""
        findings = _schema_only_findings(_FROZEN_TUTORING_SCHEMA_SQL_ONLY)
        assert [f.code for f in findings] == ["missing_persistence_code"]

    def test_h_frozen_finding_maps_to_the_new_structured_hint(self) -> None:
        from arkali.engineering.factory.stage_prompting import _structured_hint_text

        prior_findings = (
            (
                "missing_persistence_code", "backend/",
                "backend Python source contains no executable SQLite persistence",
            ),
        )
        hint = _structured_hint_text([], prior_findings)
        assert "missing_persistence_code" in hint
        assert "real, executable Python" in hint
        assert "nothing in this pipeline ever executes a bare `.sql` file" in hint

    def test_i_canonical_retry_prompt_contains_the_new_actionable_hint(self) -> None:
        """Item H/I/J: the real production `_stage_prompt` composition, not
        a reimplementation, for this exact frozen candidate's own failure,
        now carries the structured hint alongside the previous failed
        output and the Stage-2 rule."""
        from arkali.control.architecture.authority_map import AuthorityMap
        from arkali.control.specification.blueprint_engine import derive_blueprint
        from arkali.engineering.factory.stage_prompting import _stage_prompt

        goal = (
            "1. The system must persist tutors and sessions for a small home "
            "tutoring service using SQLite with at least 2 tables.\n"
            "2. The backend must expose at least 8 REST API endpoints supporting "
            "full create, read, update and delete operations for both tutors "
            "and sessions.\n"
            "3. The frontend must allow creating, viewing, editing and deleting "
            "both tutors and sessions within 2 screens.\n"
            "4. The backend must respond within 500 ms for a single record "
            "request under normal load."
        )
        blueprint = derive_blueprint(goal, AuthorityMap.load(REPO))
        declaration = StageVocabulary.load(REPO).stage("backend_schema")
        visible_files = {
            "backend/models/tutors.json": '{"table_name": "tutors", "fields": {"id": "integer"}}',
            "backend/models/sessions.json": '{"table_name": "sessions", "fields": {"id": "integer"}}',
        }
        finding_detail = "backend Python source contains no executable SQLite persistence"
        prior_findings = (("missing_persistence_code", "backend/", finding_detail),)
        prior_failure = f"missing_persistence_code:backend/:{finding_detail}"

        prompt = _stage_prompt(
            declaration, blueprint, visible_files, prior_failure, None,
            repair_strategy="structured_hint", prior_findings=prior_findings,
            previous_attempt_files=_FROZEN_TUTORING_SCHEMA_SQL_ONLY,
        )
        payload = json.loads(prompt)
        assert payload["prior_attempt_failure"] == prior_failure
        assert "backend/db/schema.sql" in payload["previous_attempt_output"]
        assert "a real, executable SQLite schema" in payload["task"]
        assert payload.get("repair_hint") is not None
        assert "missing_persistence_code" in payload["repair_hint"]

    def test_j_schema_bootstrap_unreachable_hint_is_unaffected(self) -> None:
        from arkali.engineering.factory.stage_prompting import _structured_hint_text

        prior_findings = (
            (
                "schema_bootstrap_unreachable", "backend/db.py",
                "'backend/db.py' creates real schema but no other real backend "
                "file ever imports it",
            ),
        )
        hint = _structured_hint_text([], prior_findings)
        assert "schema_bootstrap_unreachable" in hint
        assert "missing_persistence_code" not in hint

    def test_k_missing_api_routes_hint_is_unaffected(self) -> None:
        from arkali.engineering.factory.stage_prompting import _structured_hint_text

        prior_findings = (
            ("missing_api_routes", "backend/", "backend source declares no HTTP API route"),
        )
        hint = _structured_hint_text([], prior_findings)
        assert "missing_api_routes" in hint
        assert "missing_persistence_code" not in hint

    def test_l_frontend_local_import_hint_is_unaffected(self) -> None:
        from arkali.engineering.factory.stage_prompting import _structured_hint_text

        prior_findings = (
            ("frontend_local_import_unresolved", "frontend/src/App.js", "imports './Thing' but no such file exists"),
        )
        hint = _structured_hint_text([], prior_findings)
        assert "frontend_local_import_unresolved" in hint
        assert "missing_persistence_code" not in hint

    def test_m_missing_schema_bootstrap_does_not_receive_the_new_hint(self) -> None:
        """A different, distinct finding code -- persistence exists but
        never creates the schema -- must not accidentally inherit the
        `missing_persistence_code` invariant merely because both names
        mention schema/persistence. `missing_schema_bootstrap` itself has
        no hint entry either way; this only proves the new entry is not
        wrongly keyed to it."""
        from arkali.engineering.factory.stage_prompting import _SUPPORTED_HINT_INVARIANTS

        assert "missing_schema_bootstrap" not in _SUPPORTED_HINT_INVARIANTS

    def test_n_no_candidate_or_domain_literal_in_the_new_production_logic(self) -> None:
        """The rule cites its own real evidence candidate id, exactly like
        every other citation in this file (e.g. `factory-goal-mtw5byq6-
        irjabg`, `factory-ea9cba11-...`) -- that provenance string is
        expected and required. What must never leak is this specific
        candidate's own generated content: its real field/column names, or
        the hint text repeating them, which would make the fix look
        candidate-specific rather than generic."""
        from arkali.engineering.factory.stage_prompting import _SUPPORTED_HINT_INVARIANTS

        rule = self._rule()
        hint = _SUPPORTED_HINT_INVARIANTS["missing_persistence_code"]
        assert "factory-tutoring-1790697700" in rule  # real evidence citation, expected
        banned_fields = ("hourly_rate", "scheduled_time", "is_available", "duration_minutes")
        for token in banned_fields:
            assert token not in rule.lower()
            assert token not in hint.lower()


class TestAsyncEsmExportCheckerFix:
    """goal-mtzww02l-48k6h3 (session evidence, frozen). The real, terminal
    `frontend_forms` attempt 3 (recovered, unmodified, from the real
    content-addressed evidence blob `sha256:099fac5bc1570d3110c97ed0fe3d58
    fc1b979985d7b53d1cfede35e2d306a7fb`) genuinely implements real edit
    routes, real reachable create controls at empty state, and real
    `htmlFor`+`id` labels -- but `_CLIENT_INLINE_EXPORT`/
    `_INLINE_EXPORT_PATTERN` never allowed `async` between `export` and
    `function`, so the real, correctly-exported `apiClient.js` (plain ESM
    `export async function name(...)`, no CommonJS) was seen as exporting
    nothing at all, and every real, correct call/import of its 10 real
    functions was rejected as phantom or as a missing edit UI. This merges
    the real persisted `visible_files` this stage never touched (`product/
    ux_spec.json`, `frontend/src/apiClient.js`) with the real terminal
    attempt's own `stage_files` -- byte-for-byte the same merge shape
    `component_generation._generate_one_stage` uses in production -- and
    replays it through the real, unmodified `_frontend_forms_findings`
    dispatch, no model call."""

    _UX_SPEC = (
        '{"product_title": "Courier Management System", "primary_roles": '
        '["Courier Manager", "Dispatcher"], "modules": [{"name": "drivers", '
        '"navigation_label": "Drivers", "presentation": "table", "actions": '
        '["create", "edit", "delete", "view"], "forms": [{"name": '
        '"create_driver", "fields": ["name", "contact"]}, {"name": '
        '"edit_driver", "fields": ["name", "contact"]}], "search_filter": '
        'true, "states": {"loading": true, "empty": true, "error": true, '
        '"success": true}}, {"name": "orders", "navigation_label": '
        '"Orders", "presentation": "table", "actions": ["create", "edit", '
        '"delete", "view"], "forms": [{"name": "create_order", "fields": '
        '["driver_id", "destination", "status"]}, {"name": "edit_order", '
        '"fields": ["driver_id", "destination", "status"]}], '
        '"search_filter": true, "states": {"loading": true, "empty": true, '
        '"error": true, "success": true}}], "navigation_destinations": '
        '["Drivers", "Orders"], "design_system": {"typography_scale": '
        '["h1", "h2", "h3", "body", "caption"], "spacing_scale": ["xs", '
        '"sm", "md", "lg", "xl"], "component_conventions": ["button", '
        '"input", "table", "card"], "responsive": "desktop-first", '
        '"accessible_focus_contrast": true}}'
    )

    _API_CLIENT = (
        "const API_BASE_URL = 'http://localhost:5000';\n\n"
        "async function fetchWithCheck(url, options) {\n"
        "  const response = await fetch(url, options);\n"
        "  if (!response.ok) {\n"
        "    throw new Error(`HTTP error! status: ${response.status}`);\n"
        "  }\n"
        "  return response.json();\n"
        "}\n\n"
        "export async function getDrivers() {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/drivers`, { method: 'GET' });\n"
        "}\n\n"
        "export async function createDriver(driver) {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/drivers`, {\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify(driver)\n"
        "  });\n"
        "}\n\n"
        "export async function getDriver(id) {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/drivers/${id}`, { method: 'GET' });\n"
        "}\n\n"
        "export async function updateDriver(id, driver) {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/drivers/${id}`, {\n"
        "    method: 'PUT',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify(driver)\n"
        "  });\n"
        "}\n\n"
        "export async function deleteDriver(id) {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/drivers/${id}`, { method: 'DELETE' });\n"
        "}\n\n"
        "export async function getOrders() {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/orders`, { method: 'GET' });\n"
        "}\n\n"
        "export async function createOrder(order) {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/orders`, {\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify(order)\n"
        "  });\n"
        "}\n\n"
        "export async function getOrder(id) {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/orders/${id}`, { method: 'GET' });\n"
        "}\n\n"
        "export async function updateOrder(id, order) {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/orders/${id}`, {\n"
        "    method: 'PUT',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify(order)\n"
        "  });\n"
        "}\n\n"
        "export async function deleteOrder(id) {\n"
        "  return fetchWithCheck(`${API_BASE_URL}/orders/${id}`, { method: 'DELETE' });\n"
        "}\n"
    )

    _DRIVER_FORM = (
        "import React, { useState, useEffect } from 'react';\n"
        "import { useParams } from 'react-router-dom';\n"
        "import { createDriver, updateDriver } from './apiClient';\n\n"
        "const DriverForm = ({ onSubmit, initialData }) => {\n"
        "  const { id } = useParams();\n"
        "  const [formData, setFormData] = useState(initialData || {});\n"
        "  useEffect(() => { setFormData(initialData || {}); }, [initialData]);\n"
        "  const handleSubmit = async (e) => {\n"
        "    e.preventDefault();\n"
        "    if (id) { await onSubmit(id, formData); } else { await onSubmit(formData); }\n"
        "  };\n"
        "  return (\n"
        "    <form onSubmit={handleSubmit}>\n"
        "      <label htmlFor=\"name\">Name:</label>\n"
        "      <input type=\"text\" id=\"name\" name=\"name\" value={formData.name || ''} required />\n"
        "      <button type=\"submit\">{id ? 'Update Driver' : 'Create Driver'}</button>\n"
        "    </form>\n"
        "  );\n"
        "};\n\n"
        "export default DriverForm;\n"
    )

    _ORDER_FORM = (
        "import React, { useState, useEffect } from 'react';\n"
        "import { useParams } from 'react-router-dom';\n"
        "import { createOrder, updateOrder } from './apiClient';\n\n"
        "const OrderForm = ({ onSubmit, initialData }) => {\n"
        "  const { id } = useParams();\n"
        "  const [formData, setFormData] = useState(initialData || {});\n"
        "  useEffect(() => { setFormData(initialData || {}); }, [initialData]);\n"
        "  const handleSubmit = async (e) => {\n"
        "    e.preventDefault();\n"
        "    if (id) { await onSubmit(id, formData); } else { await onSubmit(formData); }\n"
        "  };\n"
        "  return (\n"
        "    <form onSubmit={handleSubmit}>\n"
        "      <label htmlFor=\"status\">Status:</label>\n"
        "      <input type=\"text\" id=\"status\" name=\"status\" value={formData.status || ''} required />\n"
        "      <button type=\"submit\">{id ? 'Update Order' : 'Create Order'}</button>\n"
        "    </form>\n"
        "  );\n"
        "};\n\n"
        "export default OrderForm;\n"
    )

    _DRIVERS_LIST = (
        "import React, { useState, useEffect } from 'react';\n"
        "import { getDrivers, createDriver } from './apiClient';\n"
        "import DriverForm from './DriverForm';\n"
        "import { Link } from 'react-router-dom';\n\n"
        "const DriversList = () => {\n"
        "  const [drivers, setDrivers] = useState([]);\n"
        "  const [showForm, setShowForm] = useState(false);\n"
        "  const handleCreate = async (driver) => { await createDriver(driver); setShowForm(false); };\n"
        "  return (\n"
        "    <div>\n"
        "      <h2>Drivers</h2>\n"
        "      {showForm && <DriverForm onSubmit={handleCreate} />}\n"
        "      {!showForm && (<button onClick={() => setShowForm(true)}>Create Driver</button>)}\n"
        "      {drivers.length === 0 ? (<div>No drivers found.</div>) : (\n"
        "        <ul>{drivers.map(driver => (\n"
        "          <li key={driver.id}>{driver.name}"
        "<Link to={`/drivers/edit/${driver.id}`}>Edit</Link>"
        "<Link to={`/drivers/delete/${driver.id}`}>Delete</Link></li>\n"
        "        ))}</ul>\n"
        "      )}\n"
        "    </div>\n"
        "  );\n"
        "};\n\n"
        "export default DriversList;\n"
    )

    _ORDERS_LIST = (
        "import React, { useState, useEffect } from 'react';\n"
        "import { getOrders, createOrder } from './apiClient';\n"
        "import OrderForm from './OrderForm';\n"
        "import { Link } from 'react-router-dom';\n\n"
        "const OrdersList = () => {\n"
        "  const [orders, setOrders] = useState([]);\n"
        "  const [showForm, setShowForm] = useState(false);\n"
        "  const handleCreate = async (order) => { await createOrder(order); setShowForm(false); };\n"
        "  return (\n"
        "    <div>\n"
        "      <h2>Orders</h2>\n"
        "      {showForm && <OrderForm onSubmit={handleCreate} />}\n"
        "      {!showForm && (<button onClick={() => setShowForm(true)}>Create Order</button>)}\n"
        "      {orders.length === 0 ? (<div>No orders found.</div>) : (\n"
        "        <ul>{orders.map(order => (\n"
        "          <li key={order.id}>{order.status}"
        "<Link to={`/orders/edit/${order.id}`}>Edit</Link>"
        "<Link to={`/orders/delete/${order.id}`}>Delete</Link></li>\n"
        "        ))}</ul>\n"
        "      )}\n"
        "    </div>\n"
        "  );\n"
        "};\n\n"
        "export default OrdersList;\n"
    )

    #: The real terminal attempt's own `App.js` -- unmodified. It calls
    #: `updateDriver(id, driver)`/`updateOrder(id, order)` directly inside
    #: its own inline route-render callbacks but never imports either name
    #: from `./apiClient` -- a real, genuine, previously-masked defect (see
    #: `test_corrected_replay_surfaces_the_real_app_js_missing_import` below).
    _APP_JS = (
        "import React from 'react';\n"
        "import { BrowserRouter as Router, Route, Switch, Link, Redirect, useParams } "
        "from 'react-router-dom';\n"
        "import DriversList from './DriversList';\n"
        "import OrdersList from './OrdersList';\n"
        "import DriverForm from './DriverForm';\n"
        "import OrderForm from './OrderForm';\n"
        "import DriverDelete from './DriverDelete';\n"
        "import OrderDelete from './OrderDelete';\n\n"
        "const App = () => {\n"
        "  return (\n"
        "    <Router>\n"
        "      <div>\n"
        "        <Switch>\n"
        "          <Route exact path=\"/drivers\" component={DriversList} />\n"
        "          <Route exact path=\"/drivers/create\" "
        "component={() => <DriverForm onSubmit={createDriver} />} />\n"
        "          <Route path=\"/drivers/edit/:id\" component={() => <DriverForm onSubmit="
        "{async (driver) => { const { id } = useParams(); await updateDriver(id, driver); }} />} />\n"
        "          <Route path=\"/drivers/delete/:id\" component={DriverDelete} />\n"
        "          <Route exact path=\"/orders\" component={OrdersList} />\n"
        "          <Route exact path=\"/orders/create\" "
        "component={() => <OrderForm onSubmit={createOrder} />} />\n"
        "          <Route path=\"/orders/edit/:id\" component={() => <OrderForm onSubmit="
        "{async (order) => { const { id } = useParams(); await updateOrder(id, order); }} />} />\n"
        "          <Route path=\"/orders/delete/:id\" component={OrderDelete} />\n"
        "        </Switch>\n"
        "      </div>\n"
        "    </Router>\n"
        "  );\n"
        "};\n\n"
        "export default App;\n"
    )

    _DRIVER_DELETE = (
        "import React, { useState } from 'react';\n"
        "import { useParams } from 'react-router-dom';\n"
        "import { deleteDriver } from './apiClient';\n\n"
        "const DriverDelete = () => {\n"
        "  const { id } = useParams();\n"
        "  const handleDelete = async () => { await deleteDriver(id); };\n"
        "  return (<button onClick={handleDelete}>Delete</button>);\n"
        "};\n\n"
        "export default DriverDelete;\n"
    )

    _ORDER_DELETE = (
        "import React, { useState } from 'react';\n"
        "import { useParams } from 'react-router-dom';\n"
        "import { deleteOrder } from './apiClient';\n\n"
        "const OrderDelete = () => {\n"
        "  const { id } = useParams();\n"
        "  const handleDelete = async () => { await deleteOrder(id); };\n"
        "  return (<button onClick={handleDelete}>Delete</button>);\n"
        "};\n\n"
        "export default OrderDelete;\n"
    )

    def _merged_files(self) -> dict[str, str]:
        #: `visible_files` (never regenerated by this stage's own attempt 3)
        #: merged with the real terminal `stage_files`, byte-for-byte the
        #: `{**visible_files, **stage_files}` shape `_generate_one_stage`
        #: itself uses.
        visible_files = {
            "product/ux_spec.json": self._UX_SPEC,
            "frontend/src/apiClient.js": self._API_CLIENT,
        }
        stage_files = {
            "frontend/src/DriverForm.js": self._DRIVER_FORM,
            "frontend/src/OrderForm.js": self._ORDER_FORM,
            "frontend/src/DriversList.js": self._DRIVERS_LIST,
            "frontend/src/OrdersList.js": self._ORDERS_LIST,
            "frontend/src/App.js": self._APP_JS,
            "frontend/src/DriverDelete.js": self._DRIVER_DELETE,
            "frontend/src/OrderDelete.js": self._ORDER_DELETE,
        }
        return {**visible_files, **stage_files}

    def test_corrected_replay_no_longer_flags_phantom_client_imports(self) -> None:
        codes = {f.code for f in _frontend_forms_findings(self._merged_files())}
        assert "frontend_phantom_client_import" not in codes

    def test_corrected_replay_no_longer_flags_missing_edit_ui(self) -> None:
        codes = {f.code for f in _frontend_forms_findings(self._merged_files())}
        assert "frontend_ui_missing_edit_ui" not in codes

    def test_corrected_replay_surfaces_the_real_app_js_missing_import(self) -> None:
        """The secondary, previously-masked real defect: fixing the
        async-export recognition gap makes `_client_call_missing_import_
        findings` accurate again, and it now correctly reports that the
        real, unmodified `App.js` calls `updateDriver`/`updateOrder`
        directly without importing either from `./apiClient` -- a real
        `ReferenceError` the moment either edit route renders. This finding
        is expected and desirable; it is not fixed by this change."""
        findings = [
            f for f in _frontend_forms_findings(self._merged_files())
            if f.code == "frontend_client_call_missing_import"
        ]
        assert len(findings) == 1
        assert findings[0].path == "frontend/src/App.js"
        assert "updateDriver" in findings[0].detail
        assert "updateOrder" in findings[0].detail

    def test_the_frozen_app_js_still_produces_the_real_finding_after_the_rule_change(
        self,
    ) -> None:
        """Section 11: the stage-9 prevention rule is generation-time
        prose only -- it must never relax what the checker itself accepts.
        The real, frozen, historical `App.js` (unpatched) must still
        produce `frontend_client_call_missing_import` exactly as before;
        this replay is evidence that the defect class the new rule text
        addresses is real, not a repair of the frozen candidate itself."""
        findings = [
            f for f in _frontend_forms_findings(self._merged_files())
            if f.code == "frontend_client_call_missing_import"
        ]
        assert len(findings) == 1
        assert findings[0].path == "frontend/src/App.js"


class TestFrontendFormsClientImportPreventionRule:
    """`FRONTEND_CLIENT_IMPORT_RULE_GAP` (real evidence: the frozen terminal
    `frontend_forms` attempt from `goal-mtzww02l-48k6h3`, no model call):
    `App.js` genuinely called `updateDriver(id, driver)`/`updateOrder(id,
    order)` and genuinely referenced `createDriver`/`createOrder` as bare
    `onSubmit={createDriver}`-style callback props, without importing any
    of the four from `./apiClient` -- a real, mechanically-confirmed
    generation-time prevention gap: `STAGED_GENERATION_STAGES.md#9`
    already required importing `useParams` for route params, but stated
    no general invariant that a called-or-referenced `frontend_client`
    export must be imported in the same file that uses it. The checker
    (`frontend_client_call_preflight.py`, already correct after the
    async-ESM-export fix), the structured retry hint
    (`_SUPPORTED_HINT_INVARIANTS["frontend_client_call_missing_import"]`,
    already adequate and unchanged), and convergence/retry-context are all
    untouched by this fix -- prose-only, additive, prevention side only."""

    @staticmethod
    def _rule() -> str:
        return StageVocabulary.load(REPO).stage("frontend_forms").rule

    def test_a_a_direct_client_call_must_be_imported_or_defined(self) -> None:
        rule = self._rule()
        assert "calls or otherwise references" in rule
        assert "updateThing(id, data)" in rule

    def test_b_a_callback_prop_reference_must_be_imported_or_defined(self) -> None:
        rule = self._rule()
        assert "onSubmit={createThing}" in rule

    def test_c_an_event_handler_reference_must_be_imported_or_defined(self) -> None:
        rule = self._rule()
        assert "onClick={deleteThing}" in rule

    def test_d_the_same_file_scope_requirement_is_explicit(self) -> None:
        rule = self._rule()
        assert "that exact same file's own scope" in rule
        assert "must be imported from its declaring module, or" in rule
        assert "otherwise defined" in rule

    def test_e_the_new_rule_text_is_generic_with_no_domain_token(self) -> None:
        rule = self._rule()
        # Only the new sentence's own generic placeholder names -- never
        # this session's real candidate domain.
        banned = ("driver", "order", "app.js", "apiclient", "courier")
        new_sentence_start = rule.index("Any real frontend_client function")
        new_sentence = rule[new_sentence_start:new_sentence_start + 400].lower()
        for token in banned:
            assert token not in new_sentence, token

    def test_f_the_existing_useparams_rule_is_preserved(self) -> None:
        rule = self._rule()
        assert "const { id } = useParams();" in rule
        assert "import `useParams` from" in rule


class TestFrontendFormsLocalImportCompletenessRule:
    """`FRONTEND_FORMS_LOCAL_COMPONENT_COMPLETENESS_GAP` (real evidence:
    `factory-goal-mu1oieg4-3bye3k`, no model call): a real, live
    candidate's own `frontend_forms` output introduced new relative
    imports for two of its own newly-referenced form components but never
    emitted either referenced file's own content, on all 4 real attempts,
    leaving a real, permanent `Module not found` build failure.
    `STAGED_GENERATION_STAGES.md#9` already required importing
    frontend_client exports and useParams, but stated no general
    invariant that a NEW local file this stage's own code imports must
    resolve inside that same response. The checker
    (`frontend_manifest_preflight.py::_frontend_local_import_findings`/
    `_relative_import_resolves`, already correct), the structured retry
    hint (`_SUPPORTED_HINT_INVARIANTS["frontend_local_import_unresolved"]`,
    added alongside this rule sentence), and parser/merge/retry-context
    are otherwise untouched by this fix -- prose-only, additive,
    prevention side plus one matching hint entry."""

    @staticmethod
    def _rule() -> str:
        return StageVocabulary.load(REPO).stage("frontend_forms").rule

    def test_a_the_same_response_resolution_requirement_is_explicit(self) -> None:
        rule = self._rule()
        assert "must resolve inside" in rule
        assert "this same response's own file set" in rule

    def test_b_the_emit_alternative_is_explicit(self) -> None:
        rule = self._rule()
        assert "emit that referenced file, with" in rule
        assert "real, working implementation content" in rule

    def test_c_the_remove_or_inline_alternative_is_explicit(self) -> None:
        rule = self._rule()
        assert "do not introduce the import at all" in rule
        assert "keep the implementation inline in" in rule
        assert "reuse an already-resolvable existing local file" in rule

    def test_d_assuming_a_later_stage_completes_it_is_explicitly_forbidden(self) -> None:
        rule = self._rule()
        assert "never assume a later stage will create it" in rule

    def test_e_the_new_sentence_carries_no_candidate_domain_token(self) -> None:
        rule = self._rule()
        banned = ("equipmentform", "rentalform", "equipment", "rental")
        start = rule.index("Any new local file this")
        new_sentence = rule[start:start + 700].lower()
        for token in banned:
            assert token not in new_sentence, token

    def test_f_the_existing_client_import_rule_is_preserved(self) -> None:
        rule = self._rule()
        assert "calls or otherwise references" in rule
        assert "updateThing(id, data)" in rule


class TestBackendImplementationFrameworkCompatibilityRule:
    """`BACKEND_ACCEPTANCE_COMPATIBILITY_GAP` (real evidence: `factory-
    goal-mu1hy9w1-qn30iv`): a real, live candidate declared
    `flask==2.3.2` and genuinely used `@app.before_first_request` -- a
    Flask lifecycle hook removed starting at Flask 2.3.0 -- to call its
    own real one-time schema setup. `backend_implementation`'s own rule
    said nothing about framework API/version compatibility, only that
    schema-creation code must actually be imported (a different, already-
    covered concern). Prose-only; the checker's own corrected invariant
    lives in `product_preflight.py::_framework_api_findings`."""

    @staticmethod
    def _rule() -> str:
        return StageVocabulary.load(REPO).stage("backend_implementation").rule

    def test_a_the_removed_hook_is_explicitly_named(self) -> None:
        rule = self._rule()
        assert "before_first_request" in rule
        assert "removed" in rule.lower()

    def test_b_the_flask_2_3_removal_boundary_is_named(self) -> None:
        rule = self._rule()
        assert "Flask 2.3" in rule

    def test_c_a_compatible_alternative_is_prescribed(self) -> None:
        rule = self._rule()
        assert "module level" in rule.lower()

    def test_d_the_existing_schema_import_rule_is_preserved(self) -> None:
        rule = self._rule()
        assert "the routes file must actually import" in rule

    def test_e_the_new_sentence_carries_no_candidate_domain_token(self) -> None:
        rule = self._rule()
        banned = ("photography", "photo session", "client_id", "studio")
        start = rule.index("Never call a")
        new_sentence = rule[start:start + 600].lower()
        for token in banned:
            assert token not in new_sentence, token


class TestFrontendUiStageScopeRule:
    """`FRONTEND_UI_UNUSED_CHECKER_STAGE_SCOPE_DEFECT` (real evidence:
    `factory-goal-mu0pvv20-b2uuo8`): `STAGED_GENERATION_STAGES.md#8`
    already exempted mutation exports from its own "the UI calls every
    non-mutating function" wording (golden-work-082) but never extended
    that same reasoning to a single-record read export -- its own real,
    natural consumer is a later record-specific detail/edit view, exactly
    as premature to require at this stage as a mutation export already
    was. Prose-only; the checker's own corrected invariant lives in
    `frontend_ux_preflight.py::_unused_client_export_findings`."""

    @staticmethod
    def _rule() -> str:
        return StageVocabulary.load(REPO).stage("frontend_ui").rule

    def test_a_a_single_record_read_export_is_explicitly_exempted(self) -> None:
        rule = self._rule()
        assert "takes an identifying argument" in rule
        assert "not this stage's concern to call merely" in rule

    def test_b_the_exemption_names_the_later_record_specific_consumer(self) -> None:
        rule = self._rule()
        assert "a later record-specific detail or edit view" in rule

    def test_c_the_collection_list_scope_is_explicit(self) -> None:
        rule = self._rule()
        assert "non-mutating (read) collection/list function" in rule
        assert "collection/list surface" in rule

    def test_d_the_existing_mutation_exemption_is_preserved(self) -> None:
        rule = self._rule()
        assert "mutating export (create/update/edit/delete) is not this stage's concern" in rule

    def test_e_the_new_sentence_carries_no_candidate_domain_token(self) -> None:
        rule = self._rule()
        banned = ("inventory", "order", "warehouse", "getinventoryitem", "getorder")
        start = rule.index("A read function whose own declared signature")
        new_sentence = rule[start:start + 500].lower()
        for token in banned:
            assert token not in new_sentence, token



def test_frozen_warehouse_frontend_ui_replay_no_longer_flags_client_unused() -> None:
    """`FRONTEND_UI_UNUSED_CHECKER_STAGE_SCOPE_DEFECT` (real evidence:
    `factory-goal-mu0pvv20-b2uuo8`, no model call). The real, frozen,
    terminal `frontend_ui` attempt's own exact bytes -- a real, correct
    `apiClient.js` declaring `getInventoryItem(id)`/`getOrder(id)`
    alongside the real `App.js`/`Inventory.js`/`Orders.js`/`index.js`
    that only ever call the bulk `getInventory()`/`getOrders()` -- must
    no longer produce `frontend_ui_client_unused` now that a
    single-record getter is exempt. Stage-scope correction, not a
    candidate-specific exception: the same real bytes, unmodified."""
    api_client = """const API_BASE_URL = 'http://localhost:5000';

async function fetchWithCheck(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function getInventory() {
  return fetchWithCheck(`${API_BASE_URL}/inventory`, { method: 'GET' });
}

export async function createInventory(item) {
  return fetchWithCheck(`${API_BASE_URL}/inventory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item)
  });
}

export async function getInventoryItem(id) {
  return fetchWithCheck(`${API_BASE_URL}/inventory/${id}`, { method: 'GET' });
}

export async function updateInventoryItem(id, item) {
  return fetchWithCheck(`${API_BASE_URL}/inventory/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item)
  });
}

export async function deleteInventoryItem(id) {
  return fetchWithCheck(`${API_BASE_URL}/inventory/${id}`, { method: 'DELETE' });
}

export async function getOrders() {
  return fetchWithCheck(`${API_BASE_URL}/orders`, { method: 'GET' });
}

export async function createOrder(order) {
  return fetchWithCheck(`${API_BASE_URL}/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(order)
  });
}

export async function getOrder(id) {
  return fetchWithCheck(`${API_BASE_URL}/orders/${id}`, { method: 'GET' });
}

export async function updateOrder(id, order) {
  return fetchWithCheck(`${API_BASE_URL}/orders/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(order)
  });
}

export async function deleteOrder(id) {
  return fetchWithCheck(`${API_BASE_URL}/orders/${id}`, { method: 'DELETE' });
}"""
    app_js = """import React, { useState, useEffect } from 'react';
import { getInventory, getOrders } from './apiClient';
import { Link } from 'react-router-dom';

const App = () => {
  const [inventory, setInventory] = useState([]);
  const [orders, setOrders] = useState([]);
  const [inventoryLoading, setInventoryLoading] = useState(true);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [inventoryError, setInventoryError] = useState(null);
  const [ordersError, setOrdersError] = useState(null);

  useEffect(() => {
    const fetchInventory = async () => {
      try {
        const data = await getInventory();
        setInventory(data);
      } catch (error) {
        setInventoryError(error.message);
      } finally {
        setInventoryLoading(false);
      }
    };

    const fetchOrders = async () => {
      try {
        const data = await getOrders();
        setOrders(data);
      } catch (error) {
        setOrdersError(error.message);
      } finally {
        setOrdersLoading(false);
      }
    };

    fetchInventory();
    fetchOrders();
  }, []);

  if (inventoryLoading || ordersLoading) {
    return <div>Loading...</div>;
  }

  if (inventoryError || ordersError) {
    return (
      <div>
        <p>Error loading data. Please try again.</p>
        <button onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }

  return (
    <div>
      <h1>Warehouse Management System</h1>
      <nav>
        <ul>
          <li><Link to="/inventory">Inventory</Link></li>
          <li><Link to="/orders">Orders</Link></li>
        </ul>
      </nav>
      <div>
        <h2>Inventory</h2>
        {inventory.length === 0 ? (
          <p>No inventory items found.</p>
        ) : (
          <ul>
            {inventory.map(item => (
              <li key={item.id}>{item.name} - Quantity: {item.quantity} - Price: ${item.price}</li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h2>Orders</h2>
        {orders.length === 0 ? (
          <p>No orders found.</p>
        ) : (
          <ul>
            {orders.map(order => (
              <li key={order.id}>Item ID: {order.item_id} - Quantity: {order.quantity} - Order Date: {order.order_date}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default App;"""
    index_js = """import React from 'react';
import ReactDOM from 'react-dom';
import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';
import App from './App';
import Inventory from './Inventory';
import Orders from './Orders';

ReactDOM.render(
  <Router>
    <Switch>
      <Route path="/inventory" component={Inventory} />
      <Route path="/orders" component={Orders} />
      <Route path="/" component={App} />
    </Switch>
  </Router>,
  document.getElementById('root')
);"""
    inventory_js = """import React, { useState, useEffect } from 'react';
import { getInventory } from './apiClient';
import { Link } from 'react-router-dom';

const Inventory = () => {
  const [inventory, setInventory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchInventory = async () => {
      try {
        const data = await getInventory();
        setInventory(data);
      } catch (error) {
        setError(error.message);
      } finally {
        setLoading(false);
      }
    };

    fetchInventory();
  }, []);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return (
      <div>
        <p>Error loading inventory. Please try again.</p>
        <button onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }

  return (
    <div>
      <h2>Inventory</h2>
      {inventory.length === 0 ? (
        <p>No inventory items found.</p>
      ) : (
        <ul>
          {inventory.map(item => (
            <li key={item.id}>{item.name} - Quantity: {item.quantity} - Price: ${item.price}</li>
          ))}
        </ul>
      )}
      <Link to="/inventory/create">Create New Inventory Item</Link>
    </div>
  );
};

export default Inventory;"""
    orders_js = """import React, { useState, useEffect } from 'react';
import { getOrders } from './apiClient';
import { Link } from 'react-router-dom';

const Orders = () => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchOrders = async () => {
      try {
        const data = await getOrders();
        setOrders(data);
      } catch (error) {
        setError(error.message);
      } finally {
        setLoading(false);
      }
    };

    fetchOrders();
  }, []);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return (
      <div>
        <p>Error loading orders. Please try again.</p>
        <button onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }

  return (
    <div>
      <h2>Orders</h2>
      {orders.length === 0 ? (
        <p>No orders found.</p>
      ) : (
        <ul>
          {orders.map(order => (
            <li key={order.id}>Item ID: {order.item_id} - Quantity: {order.quantity} - Order Date: {order.order_date}</li>
          ))}
        </ul>
      )}
      <Link to="/orders/create">Create New Order</Link>
    </div>
  );
};

export default Orders;"""
    files = {
        "frontend/src/apiClient.js": api_client,
        "frontend/src/App.js": app_js,
        "frontend/src/index.js": index_js,
        "frontend/src/Inventory.js": inventory_js,
        "frontend/src/Orders.js": orders_js,
    }
    findings = _frontend_ui_findings(files)
    assert "frontend_ui_client_unused" not in {f.code for f in findings}


def test_frozen_library_frontend_ui_replay_no_longer_flags_client_unused() -> None:
    """`FRONTEND_UI_UNUSED_CHECKER_STAGE_SCOPE_DEFECT` recurrence (real
    evidence: `factory-goal-mu183yam-d09hsx`, no model call). The real,
    frozen, terminal `frontend_ui` attempt's own exact bytes -- a real,
    correct `apiClient.js` using the CommonJS object-property async
    arrow shape (`getBook: async (id) => {...}`) alongside the real
    `App.js`/`index.js` that only ever call the bulk `getBooks()`/
    `getBorrowers()` via `apiClient.getBooks()`/`apiClient.getBorrowers()`
    property access -- must no longer produce `frontend_ui_client_unused`
    now that the arity regex recognizes this real, valid syntax shape.
    Stage-scope correction, not a candidate-specific exception: the same
    real bytes, unmodified."""
    api_client = """const axios = require('axios');

const API_BASE_URL = 'http://localhost:5000';

const apiClient = {
  getBooks: async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/books`);
      return response.data;
    } catch (error) {
      throw new Error('Failed to fetch books');
    }
  },

  createBook: async (bookData) => {
    try {
      const response = await axios.post(`${API_BASE_URL}/books`, bookData);
      return response.data;
    } catch (error) {
      throw new Error('Failed to create book');
    }
  },

  getBook: async (id) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/books/${id}`);
      return response.data;
    } catch (error) {
      throw new Error('Failed to fetch book');
    }
  },

  updateBook: async (id, bookData) => {
    try {
      const response = await axios.put(`${API_BASE_URL}/books/${id}`, bookData);
      return response.data;
    } catch (error) {
      throw new Error('Failed to update book');
    }
  },

  deleteBook: async (id) => {
    try {
      const response = await axios.delete(`${API_BASE_URL}/books/${id}`);
      return response.data;
    } catch (error) {
      throw new Error('Failed to delete book');
    }
  },

  getBorrowers: async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/borrowers`);
      return response.data;
    } catch (error) {
      throw new Error('Failed to fetch borrowers');
    }
  },

  createBorrower: async (borrowerData) => {
    try {
      const response = await axios.post(`${API_BASE_URL}/borrowers`, borrowerData);
      return response.data;
    } catch (error) {
      throw new Error('Failed to create borrower');
    }
  },

  getBorrower: async (id) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/borrowers/${id}`);
      return response.data;
    } catch (error) {
      throw new Error('Failed to fetch borrower');
    }
  },

  updateBorrower: async (id, borrowerData) => {
    try {
      const response = await axios.put(`${API_BASE_URL}/borrowers/${id}`, borrowerData);
      return response.data;
    } catch (error) {
      throw new Error('Failed to update borrower');
    }
  },

  deleteBorrower: async (id) => {
    try {
      const response = await axios.delete(`${API_BASE_URL}/borrowers/${id}`);
      return response.data;
    } catch (error) {
      throw new Error('Failed to delete borrower');
    }
  }
};

module.exports = apiClient;"""
    app_js = """import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Route, Switch, Redirect } from 'react-router-dom';
import apiClient from './apiClient';

const BooksList = () => {
  const [books, setBooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchBooks = async () => {
      try {
        const data = await apiClient.getBooks();
        setBooks(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchBooks();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error} <button onClick={() => setLoading(true)}>Retry</button></div>;
  if (books.length === 0) return <div>No books found</div>;

  return (
    <ul>
      {books.map(book => (
        <li key={book.id}>{book.title}</li>
      ))}
    </ul>
  );
};

const BorrowersList = () => {
  const [borrowers, setBorrowers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchBorrowers = async () => {
      try {
        const data = await apiClient.getBorrowers();
        setBorrowers(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchBorrowers();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error} <button onClick={() => setLoading(true)}>Retry</button></div>;
  if (borrowers.length === 0) return <div>No borrowers found</div>;

  return (
    <ul>
      {borrowers.map(borrower => (
        <li key={borrower.id}>{borrower.name}</li>
      ))}
    </ul>
  );
};

const App = () => {
  return (
    <Router>
      <div>
        <nav>
          <ul>
            <li><a href='/books'>Books</a></li>
            <li><a href='/borrowers'>Borrowers</a></li>
          </ul>
        </nav>
        <Switch>
          <Route exact path="/">
            <Redirect to="/books" />
          </Route>
          <Route path='/books' component={BooksList} />
          <Route path='/borrowers' component={BorrowersList} />
        </Switch>
      </div>
    </Router>
  );
};

export default App;"""
    index_js = """import React from 'react';
import ReactDOM from 'react-dom';
import App from './App';

ReactDOM.render(<App />, document.getElementById('root'));"""
    files = {
        "frontend/src/apiClient.js": api_client,
        "frontend/src/App.js": app_js,
        "frontend/src/index.js": index_js,
    }
    findings = _frontend_ui_findings(files)
    assert "frontend_ui_client_unused" not in {f.code for f in findings}


def test_frozen_trucking_burden_replay_uses_the_real_stage_prompt_path() -> None:
    """`FRONTEND_FORMS_TIMEOUT_BUDGET_MISMATCH` (real evidence: `factory-
    goal-mu1chcxk-nlk6u7`, no model call). Reconstructs the real
    `frontend_ui` and `frontend_forms` prompts for the exact candidate
    that genuinely timed out, using the same real `_stage_prompt`
    production helper the live pipeline itself calls -- not a hand-
    computed character count. Proves the corrected formula assigns
    `frontend_ui` its own unscaled base timeout and `frontend_forms`
    a materially larger one, from the real bytes alone."""
    app_py = "import sqlite3\nfrom flask import Flask, request, jsonify\nfrom flask_cors import CORS\nfrom backend.db import init_db, VEHICLES_SCHEMA, MAINTENANCE_SCHEMA\n\napp = Flask(__name__)\n\n# Enable CORS for all routes\nCORS(app)\n\n# Initialize the database\ninit_db()\n\n# Set up row factory for better JSON serialization\n@app.before_request\ndef before_request():\n    app.db = sqlite3.connect('trucking_company.db')\n    app.db.row_factory = sqlite3.Row\n\n@app.teardown_request\ndef teardown_request(exception):\n    if hasattr(app, 'db'):\n        app.db.close()\n\n# Vehicle routes\n@app.route('/vehicles', methods=['GET'])\ndef get_vehicles():\n    cursor = app.db.cursor()\n    cursor.execute('SELECT * FROM vehicles')\n    vehicles = [dict(row) for row in cursor.fetchall()]\n    return jsonify(vehicles)\n\n@app.route('/vehicles', methods=['POST'])\ndef create_vehicle():\n    data = request.get_json()\n    cursor = app.db.cursor()\n    cursor.execute('INSERT INTO vehicles (make, model, year, license_plate) VALUES (?, ?, ?, ?)',\n                   (data['make'], data['model'], data['year'], data['license_plate']))\n    app.db.commit()\n    vehicle_id = cursor.lastrowid\n    return jsonify({'id': vehicle_id, **data}), 201\n\n@app.route('/vehicles/<int:id>', methods=['GET'])\ndef get_vehicle(id):\n    cursor = app.db.cursor()\n    cursor.execute('SELECT * FROM vehicles WHERE id = ?', (id,))\n    vehicle = dict(cursor.fetchone()) if cursor.fetchone() else None\n    return jsonify(vehicle) if vehicle else ('', 404)\n\n@app.route('/vehicles/<int:id>', methods=['PUT'])\ndef update_vehicle(id):\n    data = request.get_json()\n    cursor = app.db.cursor()\n    cursor.execute('UPDATE vehicles SET make = ?, model = ?, year = ?, license_plate = ? WHERE id = ?',\n                   (data['make'], data['model'], data['year'], data['license_plate'], id))\n    app.db.commit()\n    return jsonify(data)\n\n@app.route('/vehicles/<int:id>', methods=['DELETE'])\ndef delete_vehicle(id):\n    cursor = app.db.cursor()\n    cursor.execute('DELETE FROM vehicles WHERE id = ?', (id,))\n    app.db.commit()\n    return '', 204\n\n# Maintenance routes\n@app.route('/maintenance', methods=['GET'])\ndef get_maintenance():\n    cursor = app.db.cursor()\n    cursor.execute('SELECT * FROM maintenance')\n    maintenance_records = [dict(row) for row in cursor.fetchall()]\n    return jsonify(maintenance_records)\n\n@app.route('/maintenance', methods=['POST'])\ndef create_maintenance():\n    data = request.get_json()\n    cursor = app.db.cursor()\n    cursor.execute('INSERT INTO maintenance (vehicle_id, date, description, cost) VALUES (?, ?, ?, ?)',\n                   (data['vehicle_id'], data['date'], data['description'], data['cost']))\n    app.db.commit()\n    maintenance_id = cursor.lastrowid\n    return jsonify({'id': maintenance_id, **data}), 201\n\n@app.route('/maintenance/<int:id>', methods=['GET'])\ndef get_maintenance_record(id):\n    cursor = app.db.cursor()\n    cursor.execute('SELECT * FROM maintenance WHERE id = ?', (id,))\n    maintenance_record = dict(cursor.fetchone()) if cursor.fetchone() else None\n    return jsonify(maintenance_record) if maintenance_record else ('', 404)\n\n@app.route('/maintenance/<int:id>', methods=['PUT'])\ndef update_maintenance_record(id):\n    data = request.get_json()\n    cursor = app.db.cursor()\n    cursor.execute('UPDATE maintenance SET vehicle_id = ?, date = ?, description = ?, cost = ? WHERE id = ?',\n                   (data['vehicle_id'], data['date'], data['description'], data['cost'], id))\n    app.db.commit()\n    return jsonify(data)\n\n@app.route('/maintenance/<int:id>', methods=['DELETE'])\ndef delete_maintenance_record(id):\n    cursor = app.db.cursor()\n    cursor.execute('DELETE FROM maintenance WHERE id = ?', (id,))\n    app.db.commit()\n    return '', 204\n\nif __name__ == '__main__':\n    app.run(debug=True)"
    db_py = '''import sqlite3

DB_NAME = 'trucking_company.db'

VEHICLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER NOT NULL,
    license_plate TEXT NOT NULL
)
"""

MAINTENANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS maintenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL,
    date DATE NOT NULL,
    description TEXT NOT NULL,
    cost FLOAT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
)
"""

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(VEHICLES_SCHEMA)
    cursor.execute(MAINTENANCE_SCHEMA)
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()'''
    vehicles_json = '{\n  "table_name": "vehicles",\n  "fields": {\n    "id": "integer",\n    "make": "string",\n    "model": "string",\n    "year": "integer",\n    "license_plate": "string"\n  }\n}'
    maintenance_json = '{\n  "table_name": "maintenance",\n  "fields": {\n    "id": "integer",\n    "vehicle_id": "integer",\n    "date": "date",\n    "description": "string",\n    "cost": "float"\n  }\n}'
    routes_json = '[\n  {\n    "path": "/vehicles",\n    "method": "GET"\n  },\n  {\n    "path": "/vehicles",\n    "method": "POST"\n  },\n  {\n    "path": "/vehicles/{id}",\n    "method": "GET"\n  },\n  {\n    "path": "/vehicles/{id}",\n    "method": "PUT"\n  },\n  {\n    "path": "/vehicles/{id}",\n    "method": "DELETE"\n  },\n  {\n    "path": "/maintenance",\n    "method": "GET"\n  },\n  {\n    "path": "/maintenance",\n    "method": "POST"\n  },\n  {\n    "path": "/maintenance/{id}",\n    "method": "GET"\n  },\n  {\n    "path": "/maintenance/{id}",\n    "method": "PUT"\n  },\n  {\n    "path": "/maintenance/{id}",\n    "method": "DELETE"\n  }\n]'
    ux_spec_json = '{"product_title": "Trucking Company Management System", "primary_roles": ["Trucking Company Administrator", "Maintenance Manager"], "modules": [{"name": "vehicles", "navigation_label": "Vehicles", "presentation": "table", "actions": ["create", "edit", "delete", "view"], "forms": [{"name": "vehicle_form", "fields": ["make", "model", "year", "license_plate"]}], "search_filter": true, "states": {"loading": true, "empty": true, "error": true, "success": true}}, {"name": "maintenance", "navigation_label": "Maintenance Records", "presentation": "table", "actions": ["create", "edit", "delete", "view"], "forms": [{"name": "maintenance_form", "fields": ["vehicle_id", "date", "description", "cost"]}], "search_filter": true, "states": {"loading": true, "empty": true, "error": true, "success": true}}], "navigation_destinations": ["Vehicles", "Maintenance Records"], "design_system": {"typography_scale": ["h1", "h2", "h3", "body", "caption"], "spacing_scale": ["xs", "sm", "md", "lg", "xl"], "component_conventions": ["button", "input", "table", "form"], "responsive": "desktop-first", "accessible_focus_contrast": true}}'
    api_client_js = "const axios = require('axios');\n\nconst API_BASE_URL = 'http://localhost:5000';\n\nconst apiClient = {\n  // Vehicle API\n  getVehicles: async () => {\n    const response = await axios.get(`${API_BASE_URL}/vehicles`);\n    return response.data;\n  },\n  createVehicle: async (vehicleData) => {\n    const response = await axios.post(`${API_BASE_URL}/vehicles`, vehicleData);\n    return response.data;\n  },\n  getVehicle: async (id) => {\n    const response = await axios.get(`${API_BASE_URL}/vehicles/${id}`);\n    return response.data;\n  },\n  updateVehicle: async (id, vehicleData) => {\n    const response = await axios.put(`${API_BASE_URL}/vehicles/${id}`, vehicleData);\n    return response.data;\n  },\n  deleteVehicle: async (id) => {\n    await axios.delete(`${API_BASE_URL}/vehicles/${id}`);\n  },\n\n  // Maintenance API\n  getMaintenanceRecords: async () => {\n    const response = await axios.get(`${API_BASE_URL}/maintenance`);\n    return response.data;\n  },\n  createMaintenanceRecord: async (maintenanceData) => {\n    const response = await axios.post(`${API_BASE_URL}/maintenance`, maintenanceData);\n    return response.data;\n  },\n  getMaintenanceRecord: async (id) => {\n    const response = await axios.get(`${API_BASE_URL}/maintenance/${id}`);\n    return response.data;\n  },\n  updateMaintenanceRecord: async (id, maintenanceData) => {\n    const response = await axios.put(`${API_BASE_URL}/maintenance/${id}`, maintenanceData);\n    return response.data;\n  },\n  deleteMaintenanceRecord: async (id) => {\n    await axios.delete(`${API_BASE_URL}/maintenance/${id}`);\n  }\n};\n\nmodule.exports = apiClient;"
    app_js = 'import React, { useState, useEffect } from \'react\';\nimport { BrowserRouter as Router, Route, Switch, Link, Redirect } from \'react-router-dom\';\nimport apiClient from \'./apiClient\';\n\nconst VehicleList = () => {\n  const [vehicles, setVehicles] = useState([]);\n  const [loading, setLoading] = useState(true);\n  const [error, setError] = useState(false);\n\n  useEffect(() => {\n    const fetchVehicles = async () => {\n      try {\n        const data = await apiClient.getVehicles();\n        setVehicles(data);\n      } catch (err) {\n        setError(true);\n      } finally {\n        setLoading(false);\n      }\n    };\n\n    fetchVehicles();\n  }, []);\n\n  if (loading) return <div>Loading...</div>;\n  if (error) return <div>Error! <button onClick={() => window.location.reload()}>Retry</button></div>;\n  if (vehicles.length === 0) return <div>No vehicles found.</div>;\n\n  return (\n    <ul>\n      {vehicles.map(vehicle => (\n        <li key={vehicle.id}>{vehicle.make} {vehicle.model}</li>\n      ))}\n    </ul>\n  );\n};\n\nconst MaintenanceList = () => {\n  const [maintenanceRecords, setMaintenanceRecords] = useState([]);\n  const [loading, setLoading] = useState(true);\n  const [error, setError] = useState(false);\n\n  useEffect(() => {\n    const fetchMaintenanceRecords = async () => {\n      try {\n        const data = await apiClient.getMaintenanceRecords();\n        setMaintenanceRecords(data);\n      } catch (err) {\n        setError(true);\n      } finally {\n        setLoading(false);\n      }\n    };\n\n    fetchMaintenanceRecords();\n  }, []);\n\n  if (loading) return <div>Loading...</div>;\n  if (error) return <div>Error! <button onClick={() => window.location.reload()}>Retry</button></div>;\n  if (maintenanceRecords.length === 0) return <div>No maintenance records found.</div>;\n\n  return (\n    <ul>\n      {maintenanceRecords.map(record => (\n        <li key={record.id}>{record.date} - {record.description}</li>\n      ))}\n    </ul>\n  );\n};\n\nconst App = () => {\n  return (\n    <Router>\n      <div>\n        <nav>\n          <ul>\n            <li><Link to="/vehicles">Vehicles</Link></li>\n            <li><Link to="/maintenance">Maintenance Records</Link></li>\n          </ul>\n        </nav>\n        <Switch>\n          <Route exact path="/">\n            <Redirect to="/vehicles" />\n          </Route>\n          <Route path="/vehicles" component={VehicleList} />\n          <Route path="/maintenance" component={MaintenanceList} />\n        </Switch>\n      </div>\n    </Router>\n  );\n};\n\nexport default App;'
    index_js = "import React from 'react';\nimport ReactDOM from 'react-dom';\nimport App from './App';\n\nReactDOM.render(<App />, document.getElementById('root'));"
    ui_visible = {
        "backend/app.py": app_py, "backend/db.py": db_py,
        "backend/models/vehicles.json": vehicles_json,
        "backend/models/maintenance.json": maintenance_json,
        "backend/routes.json": routes_json,
        "product/ux_spec.json": ux_spec_json,
        "frontend/src/apiClient.js": api_client_js,
    }
    forms_visible = {**ui_visible, "frontend/src/App.js": app_js, "frontend/src/index.js": index_js}
    ui_decl = StageVocabulary.load(REPO).stage("frontend_ui")
    forms_decl = StageVocabulary.load(REPO).stage("frontend_forms")
    goal_text = (
        "1. The system must persist vehicles and maintenance records for a small trucking "
        "company using SQLite with at least 2 tables.\n"
        "2. The backend must expose at least 8 REST API endpoints supporting full create, "
        "read, update and delete operations for both vehicles and maintenance records.\n"
        "3. The frontend must allow creating, viewing, editing and deleting both vehicles "
        "and maintenance records within 2 screens.\n"
        "4. The backend must respond within 500 ms for a single record request under "
        "normal load."
    )
    blueprint = derive_blueprint(goal_text, AuthorityMap.load(REPO))
    ui_prompt = _stage_prompt(ui_decl, blueprint, ui_visible, None, None)
    forms_prompt = _stage_prompt(forms_decl, blueprint, forms_visible, None, None)
    assert len(ui_prompt) == 13681
    # `frontend_forms`'s own rule text grew by the local-component-
    # completeness sentence (`FRONTEND_FORMS_LOCAL_COMPONENT_COMPLETENESS_
    # GAP`); this exact byte count -- and the two derived timeouts below --
    # move with it. `frontend_ui`'s own prompt is untouched.
    assert len(forms_prompt) == 20925
    ui_timeout = DEFAULT_TIMEOUT_SECONDS * min(
        max(1.0, len(ui_prompt) / _REF_PROMPT_CHARS), _MAX_TIMEOUT_SCALE)
    forms_timeout = DEFAULT_TIMEOUT_SECONDS * min(
        max(1.0, len(forms_prompt) / _REF_PROMPT_CHARS), _MAX_TIMEOUT_SCALE)
    assert ui_timeout == DEFAULT_TIMEOUT_SECONDS
    assert forms_timeout > DEFAULT_TIMEOUT_SECONDS
    assert forms_timeout == pytest.approx(1311.87, abs=0.1)
