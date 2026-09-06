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


# -- F-0082 (OBJECT_LITERAL_AT_STATEMENT_POSITION_GAP) ----------------------
#
# Real, live, independently-reproduced evidence (goal-mtoxjx1x-cwtlad and
# goal-mtpjpadj-k9auqu, frontend_client): the golden-work-054/055 class
# recurs even with the stage's own explicit prose warning present on every
# attempt and, since F-0077, the model's own exact prior rejected bytes
# shown back too. The checker already caught this as invalid JS; it never
# named the SEMANTIC reason. These tests prove the new enrichment fires
# only, and exactly, when the real distinction JavaScript's own grammar
# draws (object literal as expression vs statement) mechanically
# applies -- never a heuristic guess.


def test_enriches_the_finding_for_a_real_json_shaped_descriptor() -> None:
    source = '{\n  "getOverdueBooks": "GET /api/books/overdue"\n}'
    findings = _javascript_syntax_findings(
        {"frontend/src/apiClient.js": source}, path_prefix="frontend/src/",
    )
    assert len(findings) == 1
    assert "object literal" in findings[0].detail
    assert "never actually invoked or exported" in findings[0].detail


def test_enriches_the_finding_for_the_real_function_valued_variant_too() -> None:
    """The real, second-attempt shape (goal-mtoxjx1x-cwtlad): NOT valid
    JSON (a function value), but still a real object literal at statement
    position -- a plain JSON-validity check alone would miss this; the
    parenthesized-expression check catches it too."""
    source = (
        "{\n  \"getOverdueBooks\": function() {\n    return fetch('/api/books/overdue', {\n"
        "      method: 'GET'\n    }).then(response => response.json());\n  }\n}"
    )
    findings = _javascript_syntax_findings(
        {"frontend/src/apiClient.js": source}, path_prefix="frontend/src/",
    )
    assert len(findings) == 1
    assert "object literal" in findings[0].detail


def test_does_not_enrich_a_genuinely_unrelated_syntax_mistake() -> None:
    """A real, ordinary syntax mistake (a missing closing parenthesis) is
    NOT an object literal at statement position -- wrapping it in
    parentheses still fails, so the enrichment must never fire."""
    source = (
        "async function getOverdueBooks() {\n"
        "  const response = await axios.get('/api/books/overdue';\n"
        "  return response.data;\n}\n"
    )
    findings = _javascript_syntax_findings(
        {"frontend/src/apiClient.js": source}, path_prefix="frontend/src/",
    )
    assert len(findings) == 1
    assert "object literal" not in findings[0].detail


def test_real_valid_javascript_using_a_real_object_literal_correctly_is_silent() -> None:
    """A real object literal used CORRECTLY (assigned/exported, not bare at
    statement position) must never be flagged at all -- the enrichment
    only ever runs on content `node` has already rejected."""
    source = (
        "async function getOverdueBooks() {\n"
        "  const response = await fetch('/api/books/overdue');\n"
        "  return response.json();\n"
        "}\n"
        "module.exports = { getOverdueBooks };\n"
    )
    findings = _javascript_syntax_findings(
        {"frontend/src/apiClient.js": source}, path_prefix="frontend/src/",
    )
    assert findings == []


def test_a_second_unseen_domain_descriptor_reproduces_the_identical_enrichment() -> None:
    """Unseen-domain proof (never books/overdue, never the real Turkish
    goal's own vocabulary): the identical structural mistake in an
    unrelated inventory domain gets the identical, domain-neutral hint."""
    source = '{\n  "listWidgets": "GET /api/widgets"\n}'
    findings = _javascript_syntax_findings(
        {"frontend/src/widgetClient.js": source}, path_prefix="frontend/src/",
    )
    assert len(findings) == 1
    assert "widget" not in findings[0].detail.lower()
    assert "object literal" in findings[0].detail


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
