from __future__ import annotations

import json
import pathlib

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.blueprint_engine import derive_blueprint
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.model_product_generation import (
    generate_model_product,
    generate_model_product_bounded,
)
from arkali.engineering.localai.adapter import HonestState, InferenceResult

REPO = pathlib.Path(__file__).resolve().parents[3]
GOAL = "The system must respond within at least 200 ms."


class FixedModel:
    def __init__(self, output: str, state: HonestState = HonestState.PASS) -> None:
        self.output = output
        self.state = state

    def infer(
        self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0
    ) -> InferenceResult:
        assert "blueprint_id" in prompt
        assert timeout_seconds > 0
        return InferenceResult(
            runtime="test-runtime",
            model_id=model_id,
            state=self.state,
            detail="bounded test double",
            output=self.output,
            output_excerpt=self.output[:200],
        )


class SequencedModel:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.prompts: list[str] = []

    def infer(
        self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0
    ) -> InferenceResult:
        self.prompts.append(prompt)
        output = self.outputs[len(self.prompts) - 1]
        return InferenceResult(
            runtime="test-runtime",
            model_id=model_id,
            state=HonestState.PASS,
            detail="bounded sequence",
            output=output,
            output_excerpt=output[:200],
        )


def _workspace(tmp_path: pathlib.Path):  # noqa: ANN202
    stable = tmp_path / "stable"
    stable.mkdir()
    return WorkspaceAuthority(tmp_path / "candidates").allocate(
        workspace_id="candidate-1",
        task_id="task-1",
        agent_id="model-1",
        stable_snapshot=stable,
    )


def _valid_output() -> str:
    return json.dumps(
        {
            "files": [
                {
                    "path": "backend/app.py",
                    "content": "app = object()\n@app.route('/status')\ndef status(): return 'ok'\n",
                },
                {
                    "path": "backend/database.py",
                    "content": (
                        "import sqlite3\n"
                        "def bootstrap():\n"
                        "    sqlite3.connect('app.db').execute("
                        "'CREATE TABLE IF NOT EXISTS records (id INTEGER)')\n"
                        "bootstrap()\n"
                    ),
                },
                {"path": "backend/requirements.txt", "content": "pytest\n"},
                {"path": "frontend/index.html", "content": "<main>App</main>"},
                {"path": "frontend/src/App.js", "content": "export default function App(){}\n"},
                {"path": "frontend/package.json", "content": '{"scripts":{"build":"echo ok"}}'},
                {
                    "path": "tests/test_app.py",
                    "content": "from app import status\ndef test_app(): assert status() == 'ok'\n",
                },
                {"path": "config/README.md", "content": "run instructions\n"},
            ]
        }
    )


def test_validated_model_files_are_written_to_real_candidate_workspace(
    tmp_path: pathlib.Path,
) -> None:
    blueprint = derive_blueprint(GOAL, AuthorityMap.load(REPO))
    workspace = _workspace(tmp_path)
    result = generate_model_product(blueprint, FixedModel(_valid_output()), "model-1", workspace)

    assert len(result.files) == 8
    assert (workspace.root / "backend" / "database.py").is_file()
    assert result.runtime == "test-runtime"


def test_lossless_path_map_is_normalised_without_weakening_checks(
    tmp_path: pathlib.Path,
) -> None:
    listed = json.loads(_valid_output())["files"]
    mapped = json.dumps({"files": {item["path"]: item["content"] for item in listed}})
    result = generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(mapped),
        "model-1",
        _workspace(tmp_path),
    )
    assert result.files == tuple(item["path"] for item in listed)


def test_one_exact_json_fence_is_transport_only(tmp_path: pathlib.Path) -> None:
    result = generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(f"```json\n{_valid_output()}\n```"),
        "model-1",
        _workspace(tmp_path),
    )
    assert "backend/app.py" in result.files


def test_fence_inside_valid_json_file_content_is_not_transport_markup(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    readme = next(item for item in payload["files"] if item["path"] == "config/README.md")
    readme["content"] = "```powershell\nnpm run build\n```\n"
    result = generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(json.dumps(payload)),
        "model-1",
        _workspace(tmp_path),
    )
    assert "config/README.md" in result.files


def test_persistence_inside_backend_module_is_semantically_detected(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    payload["files"] = [item for item in payload["files"] if item["path"] != "backend/database.py"]
    payload["files"][0]["content"] = (
        "import sqlite3\n"
        "app = object()\n"
        "DB = sqlite3.connect('app.db')\n"
        "DB.execute('CREATE TABLE IF NOT EXISTS records (id INTEGER)')\n"
        "@app.route('/status')\ndef status(): return 'ok'\n"
    )
    result = generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(json.dumps(payload)),
        "model-1",
        _workspace(tmp_path),
    )
    assert "backend/app.py" in result.files


@pytest.mark.parametrize(
    "output",
    [
        "not-json",
        "commentary\n```json\n{}\n```",
        "```json\n{}\n```\nmore",
        json.dumps({"files": [{"path": "../escape", "content": "x"}]}),
        json.dumps({"files": [{"path": "backend/app.py", "content": "x"}]}),
    ],
)
def test_malformed_unsafe_or_incomplete_model_output_writes_nothing(
    tmp_path: pathlib.Path,
    output: str,
) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ModelGenerationError):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel(output),
            "model-1",
            workspace,
        )
    assert tuple(workspace.root.rglob("*.py")) == ()


def test_nonpassing_real_model_outcome_cannot_become_artifacts(
    tmp_path: pathlib.Path,
) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ModelGenerationError, match="did not pass"):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel("", HonestState.NOT_CONFIGURED),
            "model-1",
            workspace,
        )


def test_bounded_generation_feeds_semantic_failure_to_final_attempt(
    tmp_path: pathlib.Path,
) -> None:
    invalid = json.loads(_valid_output())
    database = next(item for item in invalid["files"] if item["path"] == "backend/database.py")
    database["content"] = "import sqlite3\nDB = sqlite3.connect('app.db')\n"
    model = SequencedModel([json.dumps(invalid), _valid_output()])
    result = generate_model_product_bounded(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        model,
        "model-1",
        _workspace(tmp_path),
        max_attempts=2,
    )
    assert result.attempts_used == 2
    assert "prior_attempt_failure" in model.prompts[1]
    assert "model response fails semantic preflight" in model.prompts[1]


def test_stdlib_dependency_is_mechanically_normalized_without_touching_code(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    requirements = next(
        item for item in payload["files"] if item["path"] == "backend/requirements.txt"
    )
    requirements["content"] = "Flask==3.1.0\nsqlite3\n"
    workspace = _workspace(tmp_path)
    generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(json.dumps(payload)),
        "model-1",
        workspace,
    )
    assert (workspace.root / "backend/requirements.txt").read_text() == "Flask==3.1.0\n"
    assert (workspace.root / "backend/app.py").read_text() == (
        "app = object()\n@app.route('/status')\ndef status(): return 'ok'\n"
    )


def test_double_escaped_python_transport_is_normalized_only_when_parseable(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    app = next(item for item in payload["files"] if item["path"] == "backend/app.py")
    app["content"] = app["content"].replace("\n", "\\n")
    workspace = _workspace(tmp_path)
    generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(json.dumps(payload)),
        "model-1",
        workspace,
    )
    assert "\\n" not in (workspace.root / "backend/app.py").read_text()


def test_react_scripts_entry_is_mechanically_hosted_without_rewriting_ui(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    payload["files"] = [
        item for item in payload["files"] if item["path"] != "frontend/public/index.html"
    ]
    package = next(item for item in payload["files"] if item["path"] == "frontend/package.json")
    package["content"] = '{"dependencies":{"react-scripts":"5"}}'
    workspace = _workspace(tmp_path)
    result = generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(json.dumps(payload)),
        "model-1",
        workspace,
    )
    assert "frontend/public/index.html" in result.files
    assert '<div id="root"></div>' in (workspace.root / "frontend/public/index.html").read_text()
    assert (workspace.root / "frontend/src/App.js").read_text() == (
        "export default function App(){}\n"
    )


def test_legacy_flask_requires_a_compatible_werkzeug_bound(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    requirements = next(
        item for item in payload["files"] if item["path"] == "backend/requirements.txt"
    )
    requirements["content"] = "Flask==2.0.1\nFlask-SQLAlchemy==2.5.1\n"
    with pytest.raises(ModelGenerationError, match="incompatible_dependency_range"):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel(json.dumps(payload)),
            "model-1",
            _workspace(tmp_path),
        )


def test_flask_sqlalchemy_bootstrap_requires_application_context(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    database = next(item for item in payload["files"] if item["path"] == "backend/database.py")
    database["content"] = (
        "from flask_sqlalchemy import SQLAlchemy\n"
        "db = SQLAlchemy()\n"
        "DB_URI = 'sqlite:///app.db'\n"
        "db.create_all()\n"
    )
    with pytest.raises(ModelGenerationError, match="schema_bootstrap_outside_app_context"):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel(json.dumps(payload)),
            "model-1",
            _workspace(tmp_path),
        )


def test_undefined_generated_test_fixture_is_rejected(tmp_path: pathlib.Path) -> None:
    payload = json.loads(_valid_output())
    test = next(item for item in payload["files"] if item["path"] == "tests/test_app.py")
    test["content"] = "def test_app(client): assert client is not None\n"
    with pytest.raises(ModelGenerationError, match="undefined_test_fixture"):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel(json.dumps(payload)),
            "model-1",
            _workspace(tmp_path),
        )


def test_backend_mutation_route_requires_frontend_mutation_call(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    app = next(item for item in payload["files"] if item["path"] == "backend/app.py")
    app["content"] += "@app.route('/items', methods=['POST'])\ndef create(): return 'ok'\n"
    with pytest.raises(ModelGenerationError, match="frontend_backend_contract_drift"):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel(json.dumps(payload)),
            "model-1",
            _workspace(tmp_path),
        )


def test_fetch_mutation_method_satisfies_frontend_backend_contract(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    app = next(item for item in payload["files"] if item["path"] == "backend/app.py")
    app["content"] += "@app.route('/items', methods=['PUT'])\ndef update(): return 'ok'\n"
    frontend = next(
        item for item in payload["files"] if item["path"] == "frontend/src/App.js"
    )
    frontend["content"] = "export const save = () => fetch('/items',{method:'PUT'});\n"
    result = generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(json.dumps(payload)),
        "model-1",
        _workspace(tmp_path),
    )
    assert "frontend/src/App.js" in result.files


def test_app_factory_without_server_entrypoint_is_rejected(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    app = next(item for item in payload["files"] if item["path"] == "backend/app.py")
    app["content"] = "def create_app():\n    return None\n@app.route('/x')\ndef x(): return 'x'\n"
    with pytest.raises(ModelGenerationError, match="missing_backend_entrypoint"):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel(json.dumps(payload)),
            "model-1",
            _workspace(tmp_path),
        )


def test_plain_test_import_requires_declared_dependency(tmp_path: pathlib.Path) -> None:
    payload = json.loads(_valid_output())
    requirements = next(
        item for item in payload["files"] if item["path"] == "backend/requirements.txt"
    )
    requirements["content"] = ""
    test = next(item for item in payload["files"] if item["path"] == "tests/test_app.py")
    test["content"] = "import pytest\ndef test_app(): assert pytest is not None\n"
    with pytest.raises(ModelGenerationError, match="undeclared_test_dependency"):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel(json.dumps(payload)),
            "model-1",
            _workspace(tmp_path),
        )


def test_removed_framework_hook_is_rejected_for_selected_version(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    requirements = next(
        item for item in payload["files"] if item["path"] == "backend/requirements.txt"
    )
    requirements["content"] = "Flask==3.0.0\npytest==8.0.0\n"
    app = next(item for item in payload["files"] if item["path"] == "backend/app.py")
    app["content"] += "@app.before_first_request\ndef bootstrap(): return None\n"
    with pytest.raises(ModelGenerationError, match="removed_framework_api"):
        generate_model_product(
            derive_blueprint(GOAL, AuthorityMap.load(REPO)),
            FixedModel(json.dumps(payload)),
            "model-1",
            _workspace(tmp_path),
        )


def test_fastapi_decorators_are_real_routes_and_mutation_contracts(
    tmp_path: pathlib.Path,
) -> None:
    payload = json.loads(_valid_output())
    app = next(item for item in payload["files"] if item["path"] == "backend/app.py")
    app["content"] = (
        "app = object()\n"
        "@app.get('/items')\ndef items(): return []\n"
        "@app.put('/items/{item_id}')\ndef update(item_id): return item_id\n"
    )
    frontend = next(
        item for item in payload["files"] if item["path"] == "frontend/src/App.js"
    )
    frontend["content"] = "export const update = () => fetch('/items/1',{method:'PUT'});\n"
    test = next(item for item in payload["files"] if item["path"] == "tests/test_app.py")
    test["content"] = "from app import items\ndef test_items(): assert items() == []\n"
    result = generate_model_product(
        derive_blueprint(GOAL, AuthorityMap.load(REPO)),
        FixedModel(json.dumps(payload)),
        "model-1",
        _workspace(tmp_path),
    )
    assert "backend/app.py" in result.files
