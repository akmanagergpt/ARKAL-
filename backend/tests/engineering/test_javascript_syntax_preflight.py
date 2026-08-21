from __future__ import annotations

from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings
from arkali.engineering.factory.javascript_syntax_preflight import _javascript_syntax_findings


def test_flags_a_real_json_object_masquerading_as_a_js_module() -> None:
    """golden-work-055 (session evidence, frozen): a real qwen2.5-coder:14b
    wrote frontend/src/apiClient.js as a bare JSON object literal — a
    real, node-verified SyntaxError that passed the entire pipeline
    undetected, since nothing had ever parsed frontend JS as JS."""
    source = '{\n  "getTasks": "fetch(\'/tasks\')"\n}\n'
    findings = _javascript_syntax_findings({"frontend/src/apiClient.js": source}, path_prefix="frontend/src/")
    assert len(findings) == 1
    assert findings[0].code == "javascript_syntax"
    assert findings[0].path == "frontend/src/apiClient.js"
    assert "SyntaxError" in findings[0].detail
    # The finding must never leak the internal temp file's absolute path.
    assert "AppData" not in findings[0].detail and "Temp" not in findings[0].detail


def test_is_silent_on_real_valid_javascript() -> None:
    source = "export function getTasks() { return fetch('/tasks').then(r => r.json()); }\n"
    findings = _javascript_syntax_findings({"frontend/src/apiClient.js": source}, path_prefix="frontend/src/")
    assert findings == []


def test_ignores_files_outside_the_path_prefix() -> None:
    source = "{ this is not valid js at all"
    findings = _javascript_syntax_findings({"backend/app.py": source}, path_prefix="frontend/src/")
    assert findings == []


def test_ignores_non_js_files_under_the_prefix() -> None:
    source = "{ this is not valid js at all"
    findings = _javascript_syntax_findings({"frontend/src/data.json": source}, path_prefix="frontend/src/")
    assert findings == []


def test_frontend_contract_findings_catches_the_real_golden_work_055_defect() -> None:
    """golden-work-055's exact real evidence, through the real stage
    validator this pipeline actually wires it into: the JSON-shaped
    apiClient.js satisfied the naive text-substring drift check (its
    embedded route strings happened to contain 'method: \\'POST\\'') but
    is not real, executable JavaScript."""
    files = {
        "backend/app.py": "@app.route('/tasks', methods=['POST'])\ndef create_task():\n    pass\n",
        "frontend/src/apiClient.js": (
            '{\n  "createTask": "fetch(\'/tasks\', { method: \'POST\' })"\n}\n'
        ),
    }
    findings = frontend_contract_findings(files)
    assert [f.code for f in findings] == ["javascript_syntax"]
