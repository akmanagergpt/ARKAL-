"""C-34 permission-aware browser interaction (ARK-REQ-0170: `BROWSER_LOCAL`,
`BROWSER_EXTERNAL`).

Owner: `surfaces.operations`.

AUTHORIZATION IS REAL; LAUNCH IS HONESTLY `NOT_CONFIGURED`. This host's
canonical dependency set (`backend/pyproject.toml`) declares no browser-
automation driver (no Playwright, no Selenium), so there is no real launch
mechanism to compose without introducing a new dependency this phase does
not own the decision to add. The PDP decision itself is fully real and
fully proven (`test_operations_computer_use.py`); `browse` reports the
launch step `NOT_CONFIGURED` rather than fabricating a browser session -
exactly ARK-REQ-0218/0355's own rule ("never fake a job/health/metric"),
applied to a capability this host cannot back for real. A future phase that
adds a real driver dependency composes this same decision unmodified; it
does not need a second policy path.
"""

from __future__ import annotations

from arkali.surfaces.operations.computer_use import (
    DEFAULT_TRUST_TIER,
    PolicyDecisionSource,
    authorize_computer_use_action,
)
from arkali.surfaces.operations.execution_contracts import ProcessOutcome

_NO_DRIVER = (
    "no browser-automation driver is declared in backend/pyproject.toml on "
    "this host; the PDP decision is real, the launch step is honestly "
    "NOT_CONFIGURED rather than fabricated"
)


def authorize_browser_navigation(
    pdp: PolicyDecisionSource,
    *,
    external: bool,
    trust_tier: str = DEFAULT_TRUST_TIER,
    local_only: bool = False,
    target_is_loopback: bool | None = None,
) -> ProcessOutcome:
    """The real PDP decision for one navigation - `BROWSER_LOCAL` for a
    loopback target, `BROWSER_EXTERNAL` otherwise. Never launches a browser:
    `executed` is always `False` here, since no real driver exists on this
    host to execute with (see the module docstring)."""
    operation_class = "BROWSER_EXTERNAL" if external else "BROWSER_LOCAL"
    decision = authorize_computer_use_action(
        pdp, operation_class=operation_class, trust_tier=trust_tier,
        local_only=local_only,
        facts={"target_is_loopback": target_is_loopback}
        if target_is_loopback is not None else None,
    )
    outcome = ProcessOutcome(decision=decision, executed=False)
    if decision.permits_execution:
        return outcome.model_copy(update={"stderr": _NO_DRIVER})
    return outcome


__all__ = ["authorize_browser_navigation"]
