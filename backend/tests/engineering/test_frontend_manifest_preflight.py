from __future__ import annotations

import json

from arkali.engineering.factory.frontend_manifest_preflight import (
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


def test_is_silent_on_unparseable_json() -> None:
    """A JSON-syntax defect belongs to a different check; this one must
    not raise or fabricate a finding for it."""
    assert _missing_frontend_scripts_findings({"frontend/package.json": "{not json"}) == []


def test_is_silent_when_package_json_is_absent() -> None:
    assert _missing_frontend_scripts_findings({}) == []
