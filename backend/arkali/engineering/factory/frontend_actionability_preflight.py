"""Actionability checks used by the existing frontend UX preflight.

This is an ADR-0008 budget decomposition, not a second verifier: callers remain
``frontend_ux_preflight`` and the staged-generation gate remains authoritative.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from arkali.engineering.factory.frontend_js_semantics import _balanced_brace_body
from arkali.engineering.factory.product_ux_spec import _normalize

_RECOVERY_MARKERS = ("retry", "try again", "reload", "recover", "refresh", "yeniden dene")
_CONTROL = re.compile(
    r"<(?:button|a|Link|NavLink)\b[^>]*>.*?</(?:button|a|Link|NavLink)>",
    re.DOTALL | re.IGNORECASE,
)
#: F0099_CHECKER_FALSE_NEGATIVE (real evidence: `factory-goal-mu1hy9w1-
#: qn30iv`): a real zero-record early return (`if (clients.length === 0)
#: return <div>No clients found</div>;`, `if (sessions.length === 0)
#: return ...;`) genuinely occurs, in both real modules, BEFORE the
#: real, later `return (...)` that contains the real, correctly-worded
#: `<Link to="/clients/create">Create Client</Link>` -- `_CONTROL.
#: findall(frontend)` finds that real Link anywhere in the whole,
#: concatenated frontend text regardless of which branch it sits in, so
#: this check was satisfied even though the real create control is
#: genuinely unreachable at zero records. `STAGED_GENERATION_STAGES.
#: md#9` already states the correct invariant ("an empty-state branch
#: must never hide the only path to its form"); this is checker under-
#: enforcement, not a requirement gap.
_ZERO_STATE_IF = re.compile(
    r"if\s*\(\s*(?:!\s*(\w+)\.length|(\w+)\.length\s*(?:===\s*0|<\s*1))\s*\)"
)


def _statement_end(text: str, start: int) -> int:
    """The position right after the first real top-level `;` from
    `start` -- tracking `{}`/`()`/`[]` nesting so a semicolon inside a
    JSX attribute's own inline function body (e.g. an `onClick`
    handler) is never mistaken for the end of the enclosing brace-less
    `if (...) return ...;` statement."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char in "{([":
            depth += 1
        elif char in "})]":
            depth -= 1
        elif char == ";" and depth == 0:
            return index + 1
    return len(text)


def _zero_state_branch(frontend: str, tokens: set[str]) -> str | None:
    """The real body of the first zero-record early-return branch whose
    own checked collection variable normalizes to one of this module's
    own tokens -- `None` when no such branch can be confidently located,
    so the existing whole-file behavior below is preserved unchanged
    for any candidate whose empty-state check uses a different, less
    common shape."""
    for match in _ZERO_STATE_IF.finditer(frontend):
        variable = match.group(1) or match.group(2)
        if _normalize(variable) not in tokens:
            continue
        index = match.end()
        while index < len(frontend) and frontend[index].isspace():
            index += 1
        if index < len(frontend) and frontend[index] == "{":
            return _balanced_brace_body(frontend, index)
        return frontend[match.end():_statement_end(frontend, match.end())]
    return None


def _create_access_findings(spec: object, frontend: str, finding: Callable[..., object]) -> list[object]:
    """Require a real exit from every create-capable empty state."""
    controls = _CONTROL.findall(frontend)
    findings: list[object] = []
    for module in spec.modules:  # type: ignore[attr-defined]
        if "create" not in module.actions:
            continue
        tokens = {
            _normalize(module.name), _normalize(module.navigation_label),
            _normalize(module.navigation_label.rstrip("s")),
        }
        zero_state = _zero_state_branch(frontend, tokens)
        scope = _CONTROL.findall(zero_state) if zero_state is not None else controls
        found = any(
            any(word in control.lower() for word in ("create", "add", "new"))
            and any(token and token in _normalize(control) for token in tokens)
            for control in scope
        )
        if not found:
            findings.append(finding(
                code="frontend_ui_create_unreachable_from_empty_state", path="frontend/src/",
                detail=(
                    f"module {module.name!r} declares create, but no accessible interactive "
                    "create/add/new control associated with it remains reachable; the action "
                    "must be usable even when the collection is empty"
                ),
            ))
    return findings


def _error_recovery_findings(spec: object, frontend: str, finding: Callable[..., object]) -> list[object]:
    """Require a real interactive exit from a declared recoverable error state."""
    needs_recovery = any(module.states.error for module in spec.modules)  # type: ignore[attr-defined]
    has_control = any(
        any(marker in control.lower() for marker in _RECOVERY_MARKERS)
        for control in _CONTROL.findall(frontend)
    )
    if not needs_recovery or has_control:
        return []
    return [finding(
        code="frontend_ui_error_state_not_actionable", path="frontend/src/",
        detail=(
            "product_ux_spec declares an error state, but the frontend exposes no "
            "interactive retry/reload/recovery control"
        ),
    )]


__all__ = ["_create_access_findings", "_error_recovery_findings"]
