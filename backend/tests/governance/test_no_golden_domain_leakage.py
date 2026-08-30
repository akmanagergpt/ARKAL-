"""ARK-REQ-0074 ("Golden domain logic must not enter ARKALI core"):
production pipeline code must never hardcode behavior specific to one
Golden family (today: Student/Fee Management). A real domain fact
belongs in a scenario/goal fixture (`golden/scenarios/*.json`,
`scripts/goals/*.txt`), a test fixture, or a frozen historical-evidence
comment/docstring explaining a past real defect and its real fix -- never
in the executable body of a production module, checker, prompt builder,
runner, or campaign/ledger module.

Owner: `control.architecture` (`REQUIREMENT_REGISTER.md` ARK-REQ-0074,
Phase 30, MANDATORY).

Deliberately NOT a blind substring scan: a bare `"student" in source`
check would also refuse a perfectly generic word appearing in an English
sentence with no relation to the Golden domain, and would also refuse
every real, frozen `golden-work-NNN` historical-evidence citation this
codebase already documents throughout its own checkers (session evidence
explaining exactly why a check exists is legitimate everywhere, per this
requirement's own accepted exceptions). Real docstrings (the first
statement of a module/class/function body, the standard Python
convention) and `#`-comment lines are excluded from the scan entirely --
what remains is only real, executable code, the only place a real
production leak could matter. A runtime string literal that is NOT a
docstring (an f-string built into a `SemanticFinding.detail`, a prompt
fragment, a URL path) is NOT excluded: `frontend_manifest_preflight.py`'s
own real finding text once named "EditStudent/DeleteStudent" as an
example inside exactly such a string, a real, confirmed leak this exact
mechanism must catch.
"""

from __future__ import annotations

import ast
import io
import pathlib
import tokenize
from collections.abc import Iterable

REPO = pathlib.Path(__file__).resolve().parents[3]

#: Every real production file this requirement governs. Adding a new
#: pipeline module here is expected as the codebase grows; the point is
#: never to silently exempt a new production file just because it is new.
_PRODUCTION_PYTHON_ROOTS: tuple[pathlib.Path, ...] = (
    REPO / "backend" / "arkali",
)
_PRODUCTION_SCRIPTS: tuple[pathlib.Path, ...] = (
    REPO / "scripts" / "run_staged_generation.py",
    REPO / "scripts" / "run_golden_acceptance.py",
    REPO / "scripts" / "serve_spa.py",
)
_PRODUCTION_JS: tuple[pathlib.Path, ...] = (
    REPO / "scripts" / "run_golden_browser_journey.mjs",
)

#: Real, unambiguous Student/Fee Golden domain tokens -- proper nouns and
#: compound identifiers specific to that one family, never a normal
#: English word (e.g. "student" alone is common enough prose vocabulary
#: that a false positive there would be a real nuisance; the compound/
#: qualified forms below are not).
_BANNED_TOKENS: tuple[str, ...] = (
    "studentform", "studentedit", "studentdelete", "studentlist",
    "createstudent", "updatestudent", "deletestudent", "getstudents",
    "createpayment", "getpayments", "/students", "/payments",
)


def _docstring_line_ranges(source: str) -> set[int]:
    """1-indexed source lines belonging to a REAL docstring -- the first
    statement of the module, or of a class/function body, when that
    statement is a bare string expression (the standard Python
    convention `ast.get_docstring` itself relies on). A string literal
    used anywhere else (a function argument, an f-string, a dict value)
    is not a docstring and is never included here."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    lines: set[int] = set()

    def _mark(body: list[ast.stmt]) -> None:
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            end = first.end_lineno or first.lineno
            lines.update(range(first.lineno, end + 1))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            _mark(node.body)
    return lines


def _comment_line_ranges(source: str) -> set[int]:
    lines: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                lines.add(tok.start[0])
    except (tokenize.TokenizeError, SyntaxError, IndentationError):
        pass
    return lines


def _python_leak_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    excluded = _docstring_line_ranges(source) | _comment_line_ranges(source)
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if lineno in excluded:
            continue
        lowered = line.lower()
        for token in _BANNED_TOKENS:
            if token in lowered:
                hits.append((lineno, line.strip()))
                break
    return hits


def _js_leak_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    """No AST available for a real `.mjs` file here -- the same
    line-comment exclusion this codebase's own convention already
    tolerates for structural source-text assertions elsewhere
    (`test_golden_acceptance_runner.py`)."""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("*", "//", "/**")):
            continue
        lowered = stripped.lower()
        for token in _BANNED_TOKENS:
            if token in lowered:
                hits.append((lineno, line.strip()))
                break
    return hits


def _python_files(roots: Iterable[pathlib.Path]) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in roots:
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return files


class TestNoGoldenDomainLeakageInProductionCode:
    """ARK-REQ-0074's own negative control."""

    def test_no_banned_domain_tokens_in_production_python_packages(self) -> None:
        offenders: dict[str, list[tuple[int, str]]] = {}
        for path in _python_files(_PRODUCTION_PYTHON_ROOTS):
            hits = _python_leak_lines(path)
            if hits:
                offenders[str(path.relative_to(REPO))] = hits
        assert offenders == {}, (
            "Golden domain logic (ARK-REQ-0074) found in production code outside "
            f"comments/docstrings: {offenders}"
        )

    def test_no_banned_domain_tokens_in_production_scripts(self) -> None:
        offenders: dict[str, list[tuple[int, str]]] = {}
        for path in _PRODUCTION_SCRIPTS:
            hits = _python_leak_lines(path)
            if hits:
                offenders[str(path.relative_to(REPO))] = hits
        assert offenders == {}, f"Golden domain logic found in production scripts: {offenders}"

    def test_no_banned_domain_tokens_in_production_javascript(self) -> None:
        offenders: dict[str, list[tuple[int, str]]] = {}
        for path in _PRODUCTION_JS:
            hits = _js_leak_lines(path)
            if hits:
                offenders[str(path.relative_to(REPO))] = hits
        assert offenders == {}, f"Golden domain logic found in production JS: {offenders}"

    def test_the_scan_does_not_flag_a_plain_english_word(self) -> None:
        """The narrow, compound-token allowlist must never fire on
        ordinary prose use of a common word -- proves this is not a
        blind substring check."""
        source = '"""A student of history studies the past."""\ndef f():\n    return "students"\n'
        excluded = _docstring_line_ranges(source)
        assert 1 in excluded  # the docstring line itself is excluded
        lines = source.splitlines()
        # Line 3 ("students") is real code, not a docstring -- but
        # "students" alone (no compound token) never matches the banned
        # list, which only contains qualified/compound forms.
        assert not any(token in lines[2].lower() for token in _BANNED_TOKENS)

    def test_the_scan_catches_a_synthetic_production_leak(self) -> None:
        """Proves the mechanism has real teeth: a synthetic file with a
        genuine, non-docstring, non-comment reference to a banned token
        is actually caught."""
        source = (
            '"""A real module docstring, never flagged."""\n'
            "# a comment mentioning StudentForm, never flagged\n"
            "def build():\n"
            '    return "createStudent(name, email)"\n'
        )
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = pathlib.Path(tmp_dir) / "synthetic.py"
            path.write_text(source, encoding="utf-8")
            hits = _python_leak_lines(path)
        assert len(hits) == 1
        assert hits[0][0] == 4
