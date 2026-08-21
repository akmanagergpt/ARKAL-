from __future__ import annotations

import json
import pathlib

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.blueprint_engine import derive_blueprint
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.factory.component_generation import (
    _backend_contract_findings,
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
    "backend_tests": {"tests/test_works.py": "def test_placeholder():\n    assert True\n"},
    "frontend_client": {
        "frontend/src/client.js": "export function fetchWorks() { return fetch('/works'); }\n",
    },
    "frontend_ui": {
        "frontend/src/App.js": (
            "import { fetchWorks } from './client';\n"
            "function App() { fetchWorks(); return 'loading error'; }\n"
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


def test_all_eight_stages_pass_and_are_written_to_the_real_workspace(
    tmp_path: pathlib.Path,
) -> None:
    workspace = _workspace(tmp_path)
    result = generate_staged_model_product(
        _blueprint(), _factory(_happy_path_queues()), workspace,
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 8
    written = set(result.files)
    assert written == {
        path for files in HAPPY_PATH_FILES.values() for path in files
    }
    assert (workspace.root / "backend" / "schema.py").is_file()
    assert (workspace.root / "frontend" / "src" / "App.js").is_file()


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
    # frontend_ui declares only frontend_client as an input.
    ui_prompt = factory.models["frontend_ui"].prompts[0]  # type: ignore[attr-defined]
    assert "fetchWorks" in ui_prompt  # frontend_client's real export, visible
    assert "list_works" not in ui_prompt  # backend_implementation's content, not declared


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
    assert result.attempts_used == 8
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


def test_frontend_ui_findings_passes_on_real_wiring() -> None:
    files = {
        **HAPPY_PATH_FILES["frontend_client"],
        **HAPPY_PATH_FILES["frontend_ui"],
    }
    assert _frontend_ui_findings(files) == []
