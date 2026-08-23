from __future__ import annotations

import json
import pathlib

import pytest

from arkali.engineering.factory.component_generation import (
    _backend_implementation_stage_findings,
    _backend_tests_stage_findings,
    _manifests_stage_findings,
    generate_staged_model_product,
)
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.generation_stages import StageVocabulary
from arkali.engineering.localai.adapter import HonestState
from tests.engineering.test_component_generation import (
    HAPPY_PATH_FILES,
    REPO,
    _blueprint,
    _factory,
    _happy_path_queues,
    _output,
    _workspace,
)


def test_manifests_self_heals_a_missing_werkzeug_cap_without_a_retry(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-050/051 (session evidence, frozen): the same real model
    declared flask==2.1.3 with no Werkzeug line across 8 combined attempts
    over two separate runs and never fixed it, even once told the exact
    line to add. The deterministic repair must accept this on the FIRST
    attempt — one model call, not a second retry hoping for luck — since
    the fix is unambiguous and does not need the model's judgment."""
    queues = _happy_path_queues()
    broken = _output({
        "backend/requirements.txt": "flask==2.1.3\nflask_cors==3.0.10",
        "config/README.md": "run instructions\n",
    })
    queues["manifests"] = [(HonestState.PASS, broken)]
    factory = _factory(queues)
    result = generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11
    prompts = factory.models["manifests"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 1
    written = (tmp_path / "candidates" / "staged-1" / "backend" / "requirements.txt")
    assert "Werkzeug<3" in written.read_text(encoding="utf-8")


def test_repair_applies_even_when_an_unrelated_finding_also_remains(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-060 (session evidence, frozen): manifests exhausted all
    4 attempts reporting BOTH the Werkzeug-cap gap and a real, unrelated
    missing frontend/src/index.js finding on every single attempt — real
    evidence the repair's first version only accepted itself when EVERY
    finding disappeared at once, so a real, unrelated second finding
    silently discarded a working repair every time, and feedback kept
    misreporting an already-fixed defect instead of the one real
    remaining blocker. The repair must apply regardless of what else is
    still wrong, and the next attempt's feedback must name only what is
    genuinely still wrong."""
    queues = _happy_path_queues()
    broken = _output({
        "backend/requirements.txt": "flask==2.1.3\nflask_cors==3.0.10",
        # config/README.md deliberately omitted: a second, unrelated
        # finding present alongside the repairable dependency-cap gap.
    })
    good = queues["manifests"][0]
    queues["manifests"] = [(HonestState.PASS, broken), good]
    factory = _factory(queues)
    result = generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11
    prompts = factory.models["manifests"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    assert "incompatible_dependency_range" not in prompts[1]
    assert "missing_startup_documentation" in prompts[1]


def test_frontend_forms_self_heals_a_missing_react_router_import_without_a_retry(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-084 (session evidence, frozen): a real qwen2.5-coder:14b
    reproduced golden-work-083's own exact defect byte-for-byte-similar,
    then exhausted all 4 real frontend_forms attempts on the identical
    class -- frontend/src/index.js always missing Route from its
    existing `{ BrowserRouter as Router }` import -- even once told
    exactly which file and names. The deterministic repair must accept
    this on the FIRST attempt, the same shape the Werkzeug<3 and
    react-router-version repairs already prove."""
    broken_index = (
        "import App from './App';\n"
        "import { BrowserRouter as Router } from 'react-router-dom';\n"
        "ReactDOM.render(<Router><Route path='/x'><App /></Route></Router>, "
        "document.getElementById('root'));\n"
    )
    queues = _happy_path_queues()
    queues["frontend_forms"] = [(HonestState.PASS, _output({
        **HAPPY_PATH_FILES["frontend_forms"], "frontend/src/index.js": broken_index,
    }))]
    factory = _factory(queues)
    result = generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11
    prompts = factory.models["frontend_forms"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 1
    written = tmp_path / "candidates" / "staged-1" / "frontend" / "src" / "index.js"
    assert "BrowserRouter as Router, Route" in written.read_text(encoding="utf-8")


def test_frontend_tests_config_self_heals_a_react_router_version_mismatch(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-078/079 (session evidence, frozen): frontend_ui/
    frontend_forms wrote real v5-API source (`import { Route, Switch }
    from 'react-router-dom'`) and frontend_tests_config then declared
    `react-router-dom: ^6.11.2` — a real, current, installable version
    whose own real breaking change (v6 removed Switch entirely) let a
    real production build fail outright. golden-work-079 (this session's
    first fix attempt) proved this check must live in `_manifest_findings`
    and fire at `frontend_tests_config`, not only at `manifests`:
    `manifests`' own real context (`manifest_context._manifest_context`)
    deliberately strips `frontend/src/*` to an extracted import-name list,
    so a check that depends on seeing a real `Switch` import is
    structurally blind by the time `manifests` runs — this test exercises
    the real end-to-end pipeline, `manifest_context` reduction included,
    specifically so a check wired to the wrong stage fails it."""
    v5_app = (
        "import { fetchWorks } from './client';\n"
        "import { Route, Switch } from 'react-router-dom';\n"
        "function App() { fetchWorks(); return 'loading empty error works'; }\n"
        "export default App;\n"
    )
    queues = _happy_path_queues()
    queues["frontend_ui"] = [(HonestState.PASS, _output({
        **HAPPY_PATH_FILES["frontend_ui"], "frontend/src/App.js": v5_app,
    }))]
    queues["frontend_forms"] = [(HonestState.PASS, _output({"frontend/src/App.js": v5_app}))]
    queues["frontend_tests_config"] = [(HonestState.PASS, _output({
        **HAPPY_PATH_FILES["frontend_tests_config"],
        "frontend/package.json": json.dumps({
            "dependencies": {"react-router-dom": "^6.11.2"},
        }),
    }))]
    factory = _factory(queues)
    result = generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11
    prompts = factory.models["frontend_tests_config"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 1
    written = tmp_path / "candidates" / "staged-1" / "frontend" / "package.json"
    patched = json.loads(written.read_text(encoding="utf-8"))
    assert patched["dependencies"]["react-router-dom"] == "^5.3.4"


def test_manifests_self_heals_a_react_router_version_mismatch_it_introduces_itself(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-079's second, real failure mode: `frontend_tests_config`
    leaves `react-router-dom` undeclared (a real, legal intermediate
    state — HAPPY_PATH's own happy-path package.json is just
    `{"name": "app"}`) and `manifests` itself is the one that adds
    `react-router-dom: ^6.11.2` while reconciling against the extracted
    frontend import list. This is `manifests`' own REDUCED context
    (`manifest_context._manifest_context`), the exact context that would
    have hidden the mismatch from a check depending on raw
    `frontend/src/*` text — this test exercises the real end-to-end
    retry loop specifically to prove the extracted
    `_extracted/frontend_uses_react_router_v5_switch.txt` marker closes
    that gap for real."""
    v5_app = (
        "import { fetchWorks } from './client';\n"
        "import { Route, Switch } from 'react-router-dom';\n"
        "function App() { fetchWorks(); return 'loading empty error works'; }\n"
        "export default App;\n"
    )
    queues = _happy_path_queues()
    queues["frontend_ui"] = [(HonestState.PASS, _output({
        **HAPPY_PATH_FILES["frontend_ui"], "frontend/src/App.js": v5_app,
    }))]
    queues["frontend_forms"] = [(HonestState.PASS, _output({"frontend/src/App.js": v5_app}))]
    queues["manifests"] = [(HonestState.PASS, _output({
        **HAPPY_PATH_FILES["manifests"],
        "frontend/package.json": json.dumps({
            "dependencies": {"react-router-dom": "^6.11.2"},
        }),
    }))]
    factory = _factory(queues)
    result = generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11
    prompts = factory.models["manifests"].prompts  # type: ignore[attr-defined]
    assert len(prompts) == 1
    written = tmp_path / "candidates" / "staged-1" / "frontend" / "package.json"
    patched = json.loads(written.read_text(encoding="utf-8"))
    assert patched["dependencies"]["react-router-dom"] == "^5.3.4"


def test_frontend_forms_is_rejected_for_reintroducing_a_local_import_gap(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-086/087 (session evidence, frozen): golden-work-086
    exposed App.js importing a real './Courses' module that was never
    generated, fixed by wiring `_frontend_local_import_findings` at
    `frontend_ui`. golden-work-087 then reproduced the identical real
    defect through a *different* stage: `frontend_forms` rewrote App.js
    (to wire in its own create/edit routes) and reintroduced the exact
    same unresolved import, undetected, because the check had only been
    wired at `frontend_ui` -- the same "wrong stage" class this session's
    own manifests-context lesson already named once. No deterministic
    repair exists for this (the real fix is either writing the missing
    file or removing the reference, both real application decisions), so
    this proves the real retry loop genuinely rejects and exhausts
    rather than self-healing."""
    broken_app = (
        "import { fetchWorks } from './client';\n"
        "import Missing from './Missing';\n"
        "function App() { fetchWorks(); return 'loading empty error works'; }\n"
        "export default App;\n"
    )
    queues = _happy_path_queues()
    queues["frontend_forms"] = [(HonestState.PASS, _output({"frontend/src/App.js": broken_app}))] * 4
    with pytest.raises(ModelGenerationError, match="frontend_local_import_unresolved"):
        generate_staged_model_product(
            _blueprint(), _factory(queues), _workspace(tmp_path),
            vocabulary=StageVocabulary.load(REPO),
        )


def test_frontend_forms_is_rejected_for_a_parameterized_route_no_link_ever_targets(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-088 (session evidence, frozen): frontend/src/index.js
    declared `<Route path="/students/edit/:id" component={EditStudent} />`
    -- a real, working form, confirmed correct by navigating directly to
    /students/edit/1 in a real browser -- but the real student list
    rendered a bare `<li>{student.name}</li>` with no Link, button or
    any other control anywhere in the real frontend ever constructing a
    matching URL, so a real end user could never reach a route a direct
    URL proves works. No deterministic repair exists (the real fix is
    adding a real Link/button, an application decision only the model
    can make), so this proves the real retry loop genuinely rejects and
    exhausts rather than self-healing."""
    broken_app = (
        "import { fetchWorks } from './client';\n"
        "import { Route } from 'react-router-dom';\n"
        "function App() { fetchWorks(); "
        "return (<Route path='/works/edit/:id' component={() => null} />); }\n"
        "export default App;\n"
    )
    queues = _happy_path_queues()
    queues["frontend_forms"] = [(HonestState.PASS, _output({"frontend/src/App.js": broken_app}))] * 4
    with pytest.raises(ModelGenerationError, match="frontend_route_unreachable"):
        generate_staged_model_product(
            _blueprint(), _factory(queues), _workspace(tmp_path),
            vocabulary=StageVocabulary.load(REPO),
        )


def test_anti_loop_stops_before_exhausting_the_budget_on_a_repeated_identical_finding(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-047 (session evidence, frozen): the manifests stage
    exhausted its full 4-attempt budget on the identical dependency-
    compatibility class every time, and nothing in this pipeline ever
    detected the repeat. Two consecutive attempts rejected for the exact
    identical reason must stop before spending the remaining bounded
    attempts on a call already proven to repeat."""
    queues = _happy_path_queues()
    always_bad = _output({"backend/main.py": "app = object()\n"})
    queues["backend_contract"] = [(HonestState.PASS, always_bad)] * 4
    with pytest.raises(ModelGenerationError, match="repeated the identical failure fingerprint"):
        generate_staged_model_product(
            _blueprint(), _factory(queues), _workspace(tmp_path),
            vocabulary=StageVocabulary.load(REPO),
        )


def test_anti_loop_does_not_trigger_when_findings_genuinely_differ(
    tmp_path: pathlib.Path,
) -> None:
    """A stage that fails for a different reason on each attempt is not a
    repeat, and must still be allowed to spend its full bounded budget —
    the anti-loop check must never mistake ordinary bounded retry for a
    stuck loop."""
    queues = _happy_path_queues()
    no_routes = _output({"backend/main.py": "app = object()\n"})
    no_model = _output({
        "backend/routes/task_routes.json": json.dumps([
            {"path": "/works", "method": "GET", "model_fields": ["id"]},
        ]),
    })
    good = queues["backend_contract"][0]
    queues["backend_contract"] = [
        (HonestState.PASS, no_routes), (HonestState.PASS, no_model),
        (HonestState.PASS, no_routes), good,
    ]
    result = generate_staged_model_product(
        _blueprint(), _factory(queues), _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    assert result.attempts_used == 11


def test_manifests_stage_prompt_carries_the_real_target_python_version(
    tmp_path: pathlib.Path,
) -> None:
    """golden-work-047 (session evidence, frozen): the model was never told
    what Python version its declared dependencies had to run on. Only the
    `manifests` stage's own declared rule (STAGED_GENERATION_STAGES.md)
    depends on it; every other stage's prompt is unaffected."""
    import platform

    factory = _factory(_happy_path_queues())
    generate_staged_model_product(
        _blueprint(), factory, _workspace(tmp_path),
        vocabulary=StageVocabulary.load(REPO),
    )
    manifests_prompt = factory.models["manifests"].prompts[0]  # type: ignore[attr-defined]
    assert f'"target_runtime":{{"python":"{platform.python_version()}"}}' in manifests_prompt
    backend_contract_prompt = factory.models["backend_contract"].prompts[0]  # type: ignore[attr-defined]
    assert "target_runtime" not in backend_contract_prompt


def test_backend_tests_findings_rejects_tests_nested_under_backend() -> None:
    """golden-work-048 (session evidence, frozen): a real qwen2.5-coder:14b
    placed its tests under backend/tests/test_app.py, and the check — only
    ever iterating paths that already started with tests/ — silently
    accepted it, so staged generation reached the final whole-product
    gate's required_roots check for the first time ever and failed there
    instead of at the stage that owns the defect."""
    findings = _backend_tests_stage_findings({
        "backend/tests/test_app.py": "def test_x():\n    assert True\n",
    })
    assert [f.code for f in findings] == ["backend_tests_missing_top_level_path"]


def test_backend_tests_findings_passes_on_a_real_top_level_test() -> None:
    findings = _backend_tests_stage_findings(HAPPY_PATH_FILES["backend_tests"])
    assert findings == []


def test_manifests_findings_requires_config_readme() -> None:
    """golden-work-048 (session evidence, frozen): no stage's own validator
    had ever required config/README.md, so staged generation reached the
    final whole-product gate's required_roots check for the first time
    ever and failed there instead of at the stage that owns it."""
    files = {**HAPPY_PATH_FILES["manifests"]}
    del files["config/README.md"]
    findings = _manifests_stage_findings(files)
    assert [f.code for f in findings] == ["missing_startup_documentation"]


def test_manifests_findings_passes_with_a_real_readme() -> None:
    findings = _manifests_stage_findings(HAPPY_PATH_FILES["manifests"])
    assert findings == []


def test_backend_implementation_findings_catches_a_create_route_missing_the_generated_id() -> None:
    """golden-work-052/053 (session evidence, frozen, byte-identical
    across two separate real runs): a create route returned the request
    body verbatim instead of the row id SQLite actually assigned."""
    files = {
        "backend/app.py": (
            "from flask import jsonify\n"
            "def create_task():\n"
            "    cursor.execute('INSERT INTO tasks (title) VALUES (?)', (data['title'],))\n"
            "    conn.commit()\n"
            "    return jsonify(data), 201\n"
        ),
    }
    findings = _backend_implementation_stage_findings(files)
    assert any(f.code == "missing_generated_id_in_create_response" for f in findings)
