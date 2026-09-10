"""Actionability checks used by the existing frontend UX preflight.

This is an ADR-0008 budget decomposition, not a second verifier: callers remain
``frontend_ux_preflight`` and the staged-generation gate remains authoritative.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from arkali.engineering.factory.product_ux_spec import _normalize

_RECOVERY_MARKERS = ("retry", "try again", "reload", "recover", "refresh", "yeniden dene")
_CONTROL = re.compile(
    r"<(?:button|a|Link|NavLink)\b[^>]*>.*?</(?:button|a|Link|NavLink)>",
    re.DOTALL | re.IGNORECASE,
)


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
        found = any(
            any(word in control.lower() for word in ("create", "add", "new"))
            and any(token and token in _normalize(control) for token in tokens)
            for control in controls
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
