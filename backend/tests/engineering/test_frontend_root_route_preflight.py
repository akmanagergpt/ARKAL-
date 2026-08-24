from __future__ import annotations

from arkali.engineering.factory.frontend_root_route_preflight import (
    _missing_root_route_findings,
    _orphaned_router_root_findings,
    _repair_orphaned_router_root,
)

#: golden-work-092 (session evidence, frozen), verbatim real frontend/src/index.js.
_UNREACHABLE_ROOT_INDEX_JS = """
import React from 'react';
import ReactDOM from 'react-dom';
import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';
import App from './App';
import StudentEdit from './StudentEdit';

ReactDOM.render(
  <React.StrictMode>
    <Router>
      <Switch>
        <Route path="/students/edit/:id" component={StudentEdit} />
        <Route path="/students" component={App} exact />
        <Route path="/courses" component={App} exact />
        <Route path="/payments" component={App} exact />
      </Switch>
    </Router>
  </React.StrictMode>,
  document.getElementById('root')
);
"""


def test_flags_a_switch_with_no_route_ever_reaching_the_root_path() -> None:
    """golden-work-092 (session evidence, frozen): reached
    STAGED_GENERATION_PASS, full real backend accept + npm build succeeded,
    then a real browser navigating to the app's own base URL
    (http://127.0.0.1:3000/, exactly what a deployed build serves by
    default) rendered a genuinely blank page -- document.body reduced to
    the empty <div id="root">, no console error tied to this build's own
    script hash -- because none of index.js's four real <Route>
    declarations (/students, /students/edit/:id, /courses, /payments) ever
    matches the bare root path "/". Confirmed distinct from a real defect
    by then navigating to /students, a declared route, which rendered the
    full real dashboard correctly."""
    findings = _missing_root_route_findings(
        {"frontend/src/index.js": _UNREACHABLE_ROOT_INDEX_JS}
    )
    assert len(findings) == 1
    assert findings[0].code == "frontend_root_path_unreachable"
    assert findings[0].path == "frontend/src/index.js"


def test_is_silent_when_a_route_declares_the_root_path_exactly() -> None:
    source = _UNREACHABLE_ROOT_INDEX_JS.replace(
        '<Route path="/students" component={App} exact />',
        '<Route path="/" component={App} exact />\n'
        '        <Route path="/students" component={App} exact />',
    )
    assert _missing_root_route_findings({"frontend/src/index.js": source}) == []


def test_is_silent_when_a_redirect_targets_the_root_path() -> None:
    source = _UNREACHABLE_ROOT_INDEX_JS.replace(
        "<Switch>",
        '<Switch>\n        <Redirect exact from="/" to="/students" />',
    )
    assert _missing_root_route_findings({"frontend/src/index.js": source}) == []


def test_is_silent_when_a_bare_catch_all_redirect_exists() -> None:
    """A `<Redirect>` with no `from=` attribute is a real, idiomatic v5
    default -- it matches every otherwise-unmatched path, including "/"."""
    source = _UNREACHABLE_ROOT_INDEX_JS.replace(
        "</Switch>", '        <Redirect to="/students" />\n      </Switch>',
    )
    assert _missing_root_route_findings({"frontend/src/index.js": source}) == []


def test_is_silent_when_no_router_is_used_at_all() -> None:
    """A single unconditional ReactDOM.render(<App />, ...) with no
    <Switch>/<Route> at all always renders the same component at "/" --
    not this defect."""
    source = "ReactDOM.render(<App />, document.getElementById('root'));\n"
    assert _missing_root_route_findings({"frontend/src/index.js": source}) == []


#: golden-work-097 (session evidence, frozen): App.js's own real content.
_REAL_APP_JS_WITH_ROUTER = """
import React from 'react';
import { BrowserRouter as Router, Route, Switch, Redirect } from 'react-router-dom';
import TaskList from './TaskList';
import TaskCreate from './TaskCreate';
import TaskEdit from './TaskEdit';
import TaskDelete from './TaskDelete';

const App = () => {
  return (
    <Router>
      <Switch>
        <Route exact path="/">
          <Redirect to="/tasks" />
        </Route>
        <Route exact path="/tasks" component={TaskList} />
        <Route path="/tasks/create" component={TaskCreate} />
        <Route path="/tasks/edit/:id" component={TaskEdit} />
        <Route path="/tasks/delete/:id" component={TaskDelete} />
      </Switch>
    </Router>
  );
};

export default App;
"""


def test_flags_index_js_orphaning_a_real_router_root() -> None:
    """golden-work-097 (session evidence, frozen): frontend/src/App.js
    declared a real, fully correct <Router><Switch> with all four real
    routes wired -- but frontend/src/index.js never imported or mounted
    App at all; it rendered <TaskList /> directly. A real production
    build compiled successfully and a real browser, tied to that exact
    build's own script hash, crashed outright with a real react-router
    "Invariant failed" (<Link> used with no <Router> ancestor anywhere in
    the real render tree) -- the entire app rendered nothing, and every
    route App.js declared was unreachable dead code."""
    files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": (
            "import React from 'react';\n"
            "import ReactDOM from 'react-dom';\n"
            "import TaskList from './TaskList';\n\n"
            "ReactDOM.render(<TaskList />, document.getElementById('root'));\n"
        ),
    }
    findings = _orphaned_router_root_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_router_root_orphaned"
    assert findings[0].path == "frontend/src/index.js"
    assert "App" in findings[0].detail


def test_is_silent_when_index_js_correctly_mounts_the_router_root() -> None:
    files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": (
            "import React from 'react';\n"
            "import ReactDOM from 'react-dom';\n"
            "import App from './App';\n\n"
            "ReactDOM.render(<App />, document.getElementById('root'));\n"
        ),
    }
    assert _orphaned_router_root_findings(files) == []


def test_is_silent_when_index_js_mounts_the_router_root_wrapped_in_strict_mode() -> None:
    files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": (
            "import React from 'react';\n"
            "import ReactDOM from 'react-dom';\n"
            "import App from './App';\n\n"
            "ReactDOM.render(\n"
            "  <React.StrictMode>\n"
            "    <App />\n"
            "  </React.StrictMode>,\n"
            "  document.getElementById('root')\n"
            ");\n"
        ),
    }
    assert _orphaned_router_root_findings(files) == []


def test_is_silent_when_no_other_file_declares_a_router() -> None:
    """No real router root exists anywhere else -- a single, ordinary
    component mounted directly is not this defect."""
    files = {
        "frontend/src/index.js": (
            "import App from './App';\nReactDOM.render(<App />, document.getElementById('root'));\n"
        ),
        "frontend/src/App.js": "const App = () => <div>Hello</div>;\nexport default App;\n",
    }
    assert _orphaned_router_root_findings(files) == []


def test_is_silent_when_the_router_is_declared_inline_in_index_js() -> None:
    """A router declared inline in index.js itself (no separate router-
    root file) is `_missing_root_route_findings`'s own concern, not this
    one -- index.js can never orphan a router it IS."""
    files = {
        "frontend/src/index.js": (
            "import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';\n"
            "ReactDOM.render(<Router><Switch>"
            "<Route exact path='/'><h2>Home</h2></Route>"
            "</Switch></Router>, document.getElementById('root'));\n"
        ),
    }
    assert _orphaned_router_root_findings(files) == []


_GOOD_INDEX_JS = (
    "import React from 'react';\nimport ReactDOM from 'react-dom';\n"
    "import App from './App';\n\nReactDOM.render(<App />, document.getElementById('root'));\n"
)
_BROKEN_INDEX_JS = (
    "import React from 'react';\nimport ReactDOM from 'react-dom';\n"
    "import TaskList from './TaskList';\n\n"
    "ReactDOM.render(<TaskList />, document.getElementById('root'));\n"
)


def test_repair_restores_the_known_good_prior_index_js() -> None:
    """golden-work-100/102/103 (session evidence, frozen -- the identical
    compound failure reproduced across three independent candidates, the
    last two byte-for-byte identical): frontend_ui's own attempt already
    proved index.js correctly mounts App -- frontend_forms's own stage
    rule explicitly says not to rewrite frontend_ui's own navigation, but
    a real model exhausted all 4 real attempts regenerating index.js
    incorrectly anyway."""
    visible_files = {"frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER, "frontend/src/index.js": _GOOD_INDEX_JS}
    stage_files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": _BROKEN_INDEX_JS,
        "frontend/src/TaskDelete.js": "x",
    }
    repaired = _repair_orphaned_router_root(visible_files, stage_files)
    assert repaired is not None
    assert repaired["frontend/src/index.js"] == _GOOD_INDEX_JS
    assert repaired["frontend/src/TaskDelete.js"] == "x"
    merged = {**visible_files, **repaired}
    assert _orphaned_router_root_findings(merged) == []


def test_repair_is_a_noop_when_index_js_is_already_unchanged() -> None:
    visible_files = {"frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER, "frontend/src/index.js": _GOOD_INDEX_JS}
    stage_files = {"frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER, "frontend/src/index.js": _GOOD_INDEX_JS}
    assert _repair_orphaned_router_root(visible_files, stage_files) is None


def test_repair_is_a_noop_when_the_current_version_is_not_actually_broken() -> None:
    """A real, different, legitimate rewrite of index.js that still
    correctly mounts App must never be reverted."""
    visible_files = {"frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER, "frontend/src/index.js": _GOOD_INDEX_JS}
    stage_files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": _GOOD_INDEX_JS.replace("import React from 'react';\n", ""),
    }
    assert _repair_orphaned_router_root(visible_files, stage_files) is None


def test_repair_is_a_noop_when_frontend_ui_never_declared_index_js() -> None:
    stage_files = {"frontend/src/index.js": _BROKEN_INDEX_JS}
    assert _repair_orphaned_router_root({}, stage_files) is None


def test_repair_is_a_noop_when_the_stage_did_not_write_index_js() -> None:
    visible_files = {"frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER, "frontend/src/index.js": _GOOD_INDEX_JS}
    assert _repair_orphaned_router_root(visible_files, {}) is None


#: golden-work-104 (session evidence, frozen): frontend_ui itself had no
#: router at all -- a real, legitimate single-page baseline, correct at
#: the time it was written -- so no known-good PRIOR index.js mounting
#: App can exist; frontend_forms introduced the real router root for the
#: first time in the same attempt that failed to update index.js.
_NO_ROUTER_INDEX_JS = (
    "import React from 'react';\nimport ReactDOM from 'react-dom';\n"
    "import TaskList from './TaskList';\n\n"
    "ReactDOM.render(<TaskList />, document.getElementById('root'));"
)


def test_repair_retargets_the_render_call_when_no_prior_version_helps() -> None:
    visible_files = {"frontend/src/index.js": _NO_ROUTER_INDEX_JS, "frontend/src/TaskList.js": "x"}
    stage_files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": _NO_ROUTER_INDEX_JS,
        "frontend/src/TaskDelete.js": "y",
    }
    repaired = _repair_orphaned_router_root(visible_files, stage_files)
    assert repaired is not None
    assert "<App />" in repaired["frontend/src/index.js"]
    assert "<TaskList />" not in repaired["frontend/src/index.js"]
    assert "import App from './App';" in repaired["frontend/src/index.js"]
    merged = {**visible_files, **repaired}
    assert _orphaned_router_root_findings(merged) == []


def test_retarget_repair_does_not_duplicate_an_existing_import() -> None:
    visible_files = {"frontend/src/index.js": _NO_ROUTER_INDEX_JS, "frontend/src/TaskList.js": "x"}
    stage_files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": (
            "import App from './App';\n" + _NO_ROUTER_INDEX_JS
        ),
    }
    repaired = _repair_orphaned_router_root(visible_files, stage_files)
    assert repaired is not None
    assert repaired["frontend/src/index.js"].count("import App from './App';") == 1


def test_retarget_repair_is_a_noop_when_the_router_root_is_in_a_different_directory() -> None:
    """Inventing a relative import path across directories here could
    easily be wrong -- every real candidate this session has produced
    keeps index.js and its router root in the same directory, so this
    is left for the model, not guessed."""
    visible_files = {"frontend/src/index.js": _NO_ROUTER_INDEX_JS}
    stage_files = {
        "frontend/src/pages/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": _NO_ROUTER_INDEX_JS,
    }
    assert _repair_orphaned_router_root(visible_files, stage_files) is None


def test_retarget_repair_finds_something_to_fix_when_the_stage_omits_index_js() -> None:
    """golden-work-105 (session evidence, frozen): a real qwen2.5-coder:14b
    followed frontend_forms's own "do not rewrite them" instruction so
    literally it never included frontend/src/index.js in its own
    returned files at all. Before this fix, `stage_files.get(index_path)`
    alone returned None and the whole repair silently no-op'd, even
    though the merged view (this stage's own new App.js plus
    visible_files' unmodified, pre-router index.js) still had the real
    defect. The repaired index.js must be explicitly added to the
    returned dict, since only keys a stage's own output declares are
    ever written to the workspace."""
    visible_files = {"frontend/src/index.js": _NO_ROUTER_INDEX_JS, "frontend/src/TaskList.js": "x"}
    stage_files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/TaskDelete.js": "y",
    }
    repaired = _repair_orphaned_router_root(visible_files, stage_files)
    assert repaired is not None
    assert "frontend/src/index.js" in repaired
    assert "<App />" in repaired["frontend/src/index.js"]
    merged = {**visible_files, **repaired}
    assert _orphaned_router_root_findings(merged) == []


def test_retarget_repair_is_a_noop_when_the_render_call_has_no_self_closing_tag() -> None:
    """A real shape this pipeline has not produced (a mounted component
    with children/props, not a bare self-closing tag) is left for the
    model, not guessed at."""
    visible_files = {"frontend/src/index.js": "x"}
    stage_files = {
        "frontend/src/App.js": _REAL_APP_JS_WITH_ROUTER,
        "frontend/src/index.js": (
            "ReactDOM.render(<TaskList>{children}</TaskList>, document.getElementById('root'));"
        ),
    }
    assert _repair_orphaned_router_root(visible_files, stage_files) is None
