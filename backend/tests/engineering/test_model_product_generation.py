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
                    "content": "@app.route('/status')\ndef status(): return 'ok'\n",
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
        "@app.route('/status')\ndef status(): return 'ok'\n"
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
