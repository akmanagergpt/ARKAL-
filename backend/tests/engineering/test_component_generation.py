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
    _backend_contract_findings,
    _backend_implementation_stage_findings,
    _cors_boundary_stage_findings,
    _frontend_ui_findings,
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


def _factory(per_stage: dict[str, list[tuple[HonestState, str]]]):  # noqa: ANN202
    models: dict[str, _QueueModel] = {}

    def factory(stage_name: str) -> tuple[_QueueModel, str]:
        if stage_name not in models:
            models[stage_name] = _QueueModel(per_stage[stage_name])
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
