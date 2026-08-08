"""Shared base of the security failure taxonomy (Phase 4).

Owner: kernel.contracts.

ONLY THE BASE LIVES HERE, DELIBERATELY. The concrete security failures are owned
by the contexts that raise them: policy failures by `control.policy`, tier and
backend failures by `control.isolation`. An earlier draft put all twelve types
here and pushed `kernel.contracts` to 45 public symbols against a
`max_public_surface_per_context` budget of 40. The budget was right: the kernel
was becoming a dumping ground for every taxonomy in the system, which is exactly
the "no giant module" concern expressed at context granularity.

The base is shared because a caller must be able to catch *any* security failure
without knowing which context produced it, and because `control.policy` and
`control.isolation` are both layer rank 1 and may not import each other
(`allow_same_layer: false`). Layer 0 is the only place both can reach.

FAIL CLOSED. No subclass of this may be caught and converted into a PASS, or
downgraded into a permissive decision. `UNKNOWN`, `NOT_CONFIGURED`,
`UNSUPPORTED` and `EXTERNAL_UNAVAILABLE` are never PASS and never AUTO.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import ContractViolation


class SecurityError(ContractViolation):
    """Base of the security failure taxonomy, across every security context."""

    code = "ARK-ERR-0030"
