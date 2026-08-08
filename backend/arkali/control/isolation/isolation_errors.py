"""Isolation failure taxonomy (Phase 4).

Owner: control.isolation (Protected Core). Derives from the shared
`SecurityError` base in `kernel.contracts`.

Only failures this context genuinely raises are declared. An unsatisfiable tier
is **not** an exception here: `IsolationAuthority.resolve` returns a resolution
carrying `capability_state=UNSUPPORTED` and `execution_decision=DENY`, because
"this host cannot provide TRUST-3" is a determinate answer that callers must be
able to inspect, not an error condition. Declaring an exception type that nothing
raises would be dead code pretending to be a control.
"""

from __future__ import annotations

from arkali.kernel.contracts.security_errors import SecurityError


class TrustTierViolation(SecurityError):
    """A tier was downgraded, substituted, defaulted, or a backend forged a property.

    Covers both directions of ARK-REQ-0122: a tier that is not declared, and a
    backend claiming to provide more than the canonical map says it does.
    """

    code = "ARK-ERR-0034"
