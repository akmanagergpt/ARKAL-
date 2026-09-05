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
    _apply_deterministic_repairs,
    _backend_contract_findings,
    _backend_implementation_stage_findings,
    _cors_boundary_stage_findings,
    _frontend_ui_findings,
    _parse_stage_envelope,
    generate_staged_model_product,
)
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.generation_stages import StageVocabulary
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

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0) -> InferenceResult:
        self.prompts.append(prompt)
        self.model_ids.append(model_id)
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
            "app = object()\n@app.get('/works')\ndef list_works():\n    return []\n"
            "class WorkRecord(object):\n    pass\n"
        ),
    },
    "backend_cors_boundary": {
        "backend/main.py": (
            "from flask_cors import CORS\n"
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
            "function App() { fetchWorks(); return 'loading empty error works'; }\n"
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
            "function App() { fetchWorks(); return 'loading empty error works'; }\n"
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


def test_a_syntax_error_retry_can_see_the_previous_attempts_exact_broken_line(
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
