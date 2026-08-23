from __future__ import annotations

from arkali.engineering.factory.frontend_root_route_preflight import _missing_root_route_findings

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
