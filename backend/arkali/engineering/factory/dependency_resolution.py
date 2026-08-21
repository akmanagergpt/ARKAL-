"""Deterministic backend-dependency compatibility resolution for the
`manifests` staged-generation stage.

Owner: `engineering.factory`. golden-work-047 (session evidence, frozen)
exhausted 4/4 attempts at `manifests` on the identical root-cause CLASS —
a hand-written regex table (`product_preflight._dependency_compatibility_
findings`, formerly the sole check, now `_missing_compatibility_cap_
findings` plus `_offline_dependency_compatibility_findings` below) that
knew about exactly Flask/Werkzeug/Flask-SQLAlchemy and nothing else, so
the model was given no real, general signal of what would actually
install. This module adds `pip` itself — already the standard installer
this pipeline uses elsewhere for candidates, not a new package-manager
authority — as the PRIMARY check, run in `--dry-run` mode: it resolves
the exact declared specifiers against the real package index and reports
a real conflict without writing to any environment, generated candidate,
or ARKALI's own site-packages. The conflict detail returned is `pip`'s
own explanation, never invented and never hardcoded to a golden-specific
pair, so it generalizes to any backend dependency the model declares.

WHY THE HARDCODED TABLE IS NOT SIMPLY DELETED. `pip`'s resolver only ever
sees what a package's own published metadata declares. Verified directly
(not assumed): Flask 2.0.1's real PyPI metadata declares `Werkzeug
(>=2.0)` with no upper bound at all, so `pip install Flask==2.0.1` with
Werkzeug left unpinned resolves cleanly to the current Werkzeug release —
`pip`'s own dry-run reports zero conflict — even though Flask 2.0.1 does
not run against it. This is a real, documented ecosystem gap (an
under-declared compatible range in a specific historical release), not a
resolvable-in-general problem, and no metadata-only resolver can ever see
it: the defect *is* the metadata `pip` trusts. `_missing_compatibility_
cap_findings` covers exactly this narrow, verified gap and always runs
alongside the resolver, never instead of it; only the one rule the
resolver already proves correctly (a Werkzeug pin below Flask's own
declared, accurate lower bound) is left resolver-only, reappearing in
`_offline_dependency_compatibility_findings` solely as the no-resolver
fallback so that case is not silently lost when `pip` is unavailable.

HONESTY. When the resolver cannot reach its index, or exits for any
reason other than a real, named `ResolutionImpossible` conflict, this
reports `_DependencyResolutionOutcome.NOT_CONFIGURED` — never a silent
COMPATIBLE — per this repository's own convention that an unavailable
toolchain must never be reported as PASS.
"""

from __future__ import annotations

import enum
import functools
import re
import subprocess
import sys
from collections.abc import Mapping

_PIP_TIMEOUT_SECONDS = 45.0
_CONFLICT_MARKER = "ResolutionImpossible"
_NONEXISTENT_VERSION_MARKERS = (
    "Could not find a version that satisfies the requirement",
    "No matching distribution found",
)
#: Genuine infrastructure/network unavailability — never misreported as a
#: dependency-contract defect. golden-work-049 (session evidence, frozen):
#: `flask_cors==3.1.1` was pinned to a version that has never existed on
#: PyPI; pip's real, reachable-index error for that ("Could not find a
#: version that satisfies...", populated version list, exit 1, no
#: `ResolutionImpossible`) must be distinguished from the same-shaped
#: message pip emits when it cannot reach the index at all.
_INFRA_FAILURE_MARKERS = (
    "Failed to establish a new connection", "Max retries exceeded",
    "Temporary failure in name resolution", "getaddrinfo failed",
    "Read timed out", "Connection timed out", "ConnectionError", "SSLError",
    "(from versions: none)", "(from versions: )",
)
_CAUSE_LINE = re.compile(r"(?m)^\s{4}\S.*$")
_ERROR_LINE = re.compile(r"(?m)^ERROR: .*$")

#: (code, path, detail) — mirrors `product_preflight.SemanticFinding`'s own
#: three fields without importing that class here (product_preflight.py
#: imports this module; importing back would be circular). The caller
#: wraps each tuple into a real `SemanticFinding`.
_OfflineFinding = tuple[str, str, str]


class _DependencyResolutionOutcome(enum.Enum):
    COMPATIBLE = "compatible"
    CONFLICT = "conflict"
    NOT_CONFIGURED = "not_configured"


class _DependencyResolutionResult:
    __slots__ = ("outcome", "detail")

    def __init__(self, outcome: _DependencyResolutionOutcome, detail: str) -> None:
        self.outcome = outcome
        self.detail = detail


def _parse_requirement_specifiers(requirements_text: str) -> list[str]:
    """Exact `pip`-installable specifiers declared in a requirements.txt
    body — one per real declared line; comments, blank lines and
    `-`/`.`-prefixed options dropped. Never invented: every specifier
    returned is a real declared line, unchanged."""
    specifiers: list[str] = []
    for line in requirements_text.splitlines():
        declared = line.split("#", 1)[0].strip()
        if not declared or declared.startswith(("-", ".")):
            continue
        specifiers.append(declared)
    return specifiers


def _extract_conflict_reason(pip_output: str) -> str:
    """`pip`'s own real conflict explanation (its "The conflict is caused
    by:" block), trimmed to the indented cause lines — never paraphrased,
    never invented."""
    marker = "The conflict is caused by:"
    if marker not in pip_output:
        return pip_output.strip()[:400]
    tail = pip_output.split(marker, 1)[1]
    lines = [match.group(0).strip() for match in _CAUSE_LINE.finditer(tail)]
    return "; ".join(lines) if lines else tail.strip()[:400]


def _extract_error_lines(pip_output: str) -> str:
    """`pip`'s own real `ERROR:` lines, verbatim — used for a failure that
    is a genuine unsatisfiable requirement (a pinned version that does not
    exist) but is not shaped like a `ResolutionImpossible` cross-package
    conflict, so `_extract_conflict_reason`'s marker-anchored parse would
    find nothing."""
    lines = [match.group(0).strip() for match in _ERROR_LINE.finditer(pip_output)]
    return "; ".join(lines) if lines else pip_output.strip()[:400]


@functools.lru_cache(maxsize=256)
def _resolve_specifiers(specifiers: tuple[str, ...]) -> _DependencyResolutionResult:
    """The real subprocess call, memoized by its exact specifier set —
    dozens of stage attempts and test cases declare the identical small
    dependency set, and a real network round trip per identical set would
    make every caller (including this repository's own test suite) both
    slow and network-flaky for no new information. Safe: the declared
    specifiers are exact (`==` pins or bare names resolved once per real
    process lifetime), not a moving target within one run."""
    command = [
        sys.executable, "-m", "pip", "install", "--dry-run", "--quiet",
        "--disable-pip-version-check", "--no-input", "--no-cache-dir",
        *specifiers,
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=_PIP_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return _DependencyResolutionResult(
            _DependencyResolutionOutcome.NOT_CONFIGURED,
            f"dependency resolver unavailable: {error}",
        )
    if completed.returncode == 0:
        return _DependencyResolutionResult(_DependencyResolutionOutcome.COMPATIBLE, "")
    output = completed.stderr or completed.stdout
    if any(marker in output for marker in _INFRA_FAILURE_MARKERS):
        return _DependencyResolutionResult(
            _DependencyResolutionOutcome.NOT_CONFIGURED,
            f"dependency resolver could not reach its package index: {output.strip()[:400]}",
        )
    if _CONFLICT_MARKER in output:
        return _DependencyResolutionResult(
            _DependencyResolutionOutcome.CONFLICT, _extract_conflict_reason(output),
        )
    if any(marker in output for marker in _NONEXISTENT_VERSION_MARKERS):
        # golden-work-049 (session evidence, frozen): flask_cors==3.1.1 was
        # pinned to a version that has never existed on PyPI — a real,
        # reachable-index `pip` failure (populated version list in the
        # message), not a cross-package `ResolutionImpossible` conflict,
        # so it needs its own classification rather than falling through
        # to NOT_CONFIGURED and being silently unreported.
        return _DependencyResolutionResult(
            _DependencyResolutionOutcome.CONFLICT, _extract_error_lines(output),
        )
    return _DependencyResolutionResult(
        _DependencyResolutionOutcome.NOT_CONFIGURED,
        f"dependency resolver did not return a real conflict verdict: {output.strip()[:400]}",
    )


def _resolve_backend_dependency_contract(
    requirements_text: str,
) -> _DependencyResolutionResult:
    """Real, general dependency-compatibility ground truth for a declared
    `backend/requirements.txt` body, sourced from `pip`'s own resolver
    running against this host's real package index in `--dry-run` mode —
    the same host every generated candidate is actually installed and run
    on, so no cross-version target flag is needed. Resolves nothing to
    disk; installs nothing; never touches the generated candidate."""
    specifiers = _parse_requirement_specifiers(requirements_text)
    if not specifiers:
        return _DependencyResolutionResult(_DependencyResolutionOutcome.COMPATIBLE, "")
    return _resolve_specifiers(tuple(sorted(specifiers)))


#: (exact patch line to append, actionable finding detail) — one entry
#: per verified ecosystem gap. Shared by the finding function and the
#: deterministic repair below so both stay in sync with the same real,
#: verified detection logic rather than two independent copies.
def _needed_compatibility_cap_patches(lowered: str) -> list[tuple[str, str]]:
    patches: list[tuple[str, str]] = []
    flask_match = re.search(r"(?m)^flask\s*==\s*(\d+)\.(\d+)", lowered)
    werkzeug_cap = re.search(r"(?m)^werkzeug\s*[^\n]*<\s*3(?:\.0+)?(?:\s|$)", lowered)
    if flask_match and tuple(map(int, flask_match.groups())) < (2, 2) and not werkzeug_cap:
        patches.append((
            "Werkzeug<3",
            "add a line 'Werkzeug<3' to backend/requirements.txt, or change the "
            "flask line to 'flask>=2.2'",
        ))
    sqlalchemy_extension = re.search(r"(?m)^flask_sqlalchemy\s*==\s*(\d+)\.(\d+)", lowered)
    sqlalchemy_cap = re.search(r"(?m)^sqlalchemy\s*[^\n]*<\s*2(?:\.0+)?(?:\s|$)", lowered)
    if (
        sqlalchemy_extension
        and tuple(map(int, sqlalchemy_extension.groups())) < (3, 0)
        and not sqlalchemy_cap
    ):
        patches.append((
            "SQLAlchemy<2",
            "add a line 'SQLAlchemy<2' to backend/requirements.txt, or change the "
            "flask_sqlalchemy line to 'flask_sqlalchemy>=3'",
        ))
    return patches


def _missing_compatibility_cap_findings(lowered: str) -> list[_OfflineFinding]:
    """Real, verified ecosystem gaps a metadata-only resolver structurally
    cannot see (see module docstring): a package's own published metadata
    under-declares its true compatible upper bound. Always runs alongside
    the real resolver, independent of its availability or verdict.
    `lowered` is `requirements.txt`'s text, already lowercased with `-`
    normalized to `_`, matching `product_preflight._declared_dependencies`'s
    own convention. ACTIONABLE, not just diagnostic (golden-work-050,
    session evidence, frozen: the model was told the requirement
    abstractly and never added the fix across 4 attempts)."""
    return [
        ("incompatible_dependency_range", "backend/requirements.txt", detail)
        for _, detail in _needed_compatibility_cap_patches(lowered)
    ]


def _repair_missing_compatibility_cap(requirements_text: str) -> str | None:
    """Deterministic, mechanical repair for exactly the gap class
    `_missing_compatibility_cap_findings` verified is both necessary and
    sufficient — never a guess, never a version invented. golden-work-050
    and golden-work-051 (session evidence, frozen): the same real model
    failed to add this itself across 8 combined attempts over two
    separate runs, even after being told the exact line to add
    (golden-work-051's own last attempt is byte-identical to
    golden-work-050's). Per D-027's own separation of "the model declares
    what it needs" from "ARKALI's deterministic layer produces the
    validated contract": once the exact, unambiguous fix for a real,
    verified defect is known, applying it and re-validating is more
    honest than another blind model retry against a budget already shown
    not to converge. Returns the patched text, or None if no known
    ecosystem-gap repair applies — never patches a real cross-package
    `pip` conflict, which has no single unambiguous fix."""
    lowered = requirements_text.lower().replace("-", "_")
    patches = _needed_compatibility_cap_patches(lowered)
    if not patches:
        return None
    addition = "\n".join(line for line, _ in patches)
    return requirements_text.rstrip("\n") + "\n" + addition + "\n"


def _apply_missing_compatibility_cap_repair(
    stage_files: Mapping[str, str],
) -> dict[str, str] | None:
    """`_repair_missing_compatibility_cap` for one stage's own new output:
    repairs only `backend/requirements.txt`, and only when THIS stage
    just wrote it. Does not validate the result — the caller re-runs its
    own real stage check over the repaired files before trusting it,
    exactly as it already does for the model's own unrepaired output."""
    requirements = stage_files.get("backend/requirements.txt")
    if requirements is None:
        return None
    patched = _repair_missing_compatibility_cap(requirements)
    if patched is None:
        return None
    return {**stage_files, "backend/requirements.txt": patched}


def _offline_dependency_compatibility_findings(lowered: str) -> list[_OfflineFinding]:
    """Full fallback used only when the real resolver
    (`_resolve_backend_dependency_contract`) cannot be consulted at all —
    e.g. no network — so its own genuinely-caught case (a Werkzeug pin
    below Flask's own declared, accurate lower bound; golden-work-047's
    exact class) is not silently lost. Always-on findings from
    `_missing_compatibility_cap_findings` plus that one resolver-only
    rule restated."""
    findings = list(_missing_compatibility_cap_findings(lowered))
    flask_match = re.search(r"(?m)^flask\s*==\s*(\d+)\.(\d+)", lowered)
    werkzeug_match = re.search(r"(?m)^werkzeug\s*==\s*(\d+)\.(\d+)", lowered)
    if (
        flask_match
        and werkzeug_match
        and tuple(map(int, flask_match.groups())) >= (2, 2)
        and tuple(map(int, werkzeug_match.groups())) < (2, 2)
    ):
        findings.append((
            "incompatible_dependency_range", "backend/requirements.txt",
            "Flask 2.2 and newer require Werkzeug 2.2 or newer",
        ))
    return findings
