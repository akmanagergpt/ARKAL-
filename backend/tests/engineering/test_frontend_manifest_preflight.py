from __future__ import annotations

import json

from arkali.engineering.factory.frontend_manifest_preflight import (
    _missing_frontend_entry_point_findings,
    _missing_frontend_scripts_findings,
)


def test_flags_react_scripts_declared_without_a_scripts_object() -> None:
    """golden-work-058 (session evidence, frozen): real npm install
    succeeded, then real `npm run build` failed outright with "Missing
    script: build" — package.json declared react-scripts as a dependency
    but had no scripts object at all."""
    package = json.dumps({
        "name": "react-app", "dependencies": {"react-scripts": "4.0.3"},
    })
    findings = _missing_frontend_scripts_findings({"frontend/package.json": package})
    assert len(findings) == 1
    assert findings[0].code == "missing_frontend_runnable_scripts"
    assert "start" in findings[0].detail and "build" in findings[0].detail


def test_flags_a_scripts_object_missing_just_build() -> None:
    package = json.dumps({
        "dependencies": {"react-scripts": "4.0.3"},
        "scripts": {"start": "react-scripts start"},
    })
    findings = _missing_frontend_scripts_findings({"frontend/package.json": package})
    assert len(findings) == 1
    assert "['build']" in findings[0].detail


def test_is_silent_when_both_scripts_are_declared() -> None:
    package = json.dumps({
        "dependencies": {"react-scripts": "4.0.3"},
        "scripts": {"start": "react-scripts start", "build": "react-scripts build"},
    })
    assert _missing_frontend_scripts_findings({"frontend/package.json": package}) == []


def test_is_silent_when_react_scripts_is_not_declared() -> None:
    package = json.dumps({"name": "vanilla-app"})
    assert _missing_frontend_scripts_findings({"frontend/package.json": package}) == []


def test_flags_scripts_referencing_react_scripts_with_no_such_dependency() -> None:
    """golden-work-070 (session evidence, frozen): package.json's own
    scripts called "react-scripts build"/"react-scripts start", but
    react-scripts was declared in neither dependencies nor
    devDependencies. npm install silently installed only
    react/react-dom/react-router-dom (19 packages, not the ~1800
    react-scripts pulls in) and the real npm run build failed outright:
    "'react-scripts' is not recognized as an internal or external
    command". The old check's bare substring test on the raw file text
    never caught this -- the scripts commands themselves already contain
    the substring "react-scripts"."""
    package = json.dumps({
        "dependencies": {"react": "^17.0.2", "react-dom": "^17.0.2"},
        "scripts": {"start": "react-scripts start", "build": "react-scripts build"},
    })
    findings = _missing_frontend_scripts_findings({"frontend/package.json": package})
    assert len(findings) == 1
    assert findings[0].code == "missing_react_scripts_dependency"


def test_is_silent_when_react_scripts_is_a_real_dev_dependency() -> None:
    package = json.dumps({
        "dependencies": {"react": "^17.0.2"},
        "devDependencies": {"react-scripts": "4.0.3"},
        "scripts": {"start": "react-scripts start", "build": "react-scripts build"},
    })
    assert _missing_frontend_scripts_findings({"frontend/package.json": package}) == []


def test_is_silent_on_unparseable_json() -> None:
    """A JSON-syntax defect belongs to a different check; this one must
    not raise or fabricate a finding for it."""
    assert _missing_frontend_scripts_findings({"frontend/package.json": "{not json"}) == []


def test_is_silent_when_package_json_is_absent() -> None:
    assert _missing_frontend_scripts_findings({}) == []


def test_flags_missing_index_js() -> None:
    """golden-work-059 (session evidence, frozen): real npm install and
    real npm run build both ran for the first time (row 354's scripts fix
    confirmed working), then react-scripts build failed outright with
    "Could not find a required file. Name: index.js." -- its webpack
    config hard-codes this exact path as the entry point. Unconditional,
    not gated on react-scripts (golden-work-061, session evidence,
    frozen): checked at frontend_ui, which has no visibility into
    package.json yet -- that is declared later, at manifests."""
    findings = _missing_frontend_entry_point_findings({"frontend/src/App.js": "x"})
    assert len(findings) == 1
    assert findings[0].code == "missing_frontend_entry_point"
    assert findings[0].path == "frontend/src/index.js"


def test_entry_point_check_is_silent_when_index_js_exists() -> None:
    files = {"frontend/src/App.js": "x", "frontend/src/index.js": "ReactDOM.render(1,2);"}
    assert _missing_frontend_entry_point_findings(files) == []
