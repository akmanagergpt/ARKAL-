"""Policy failure taxonomy (Phase 4).

Owner: control.policy (Protected Core). Derives from the shared
`SecurityError` base in `kernel.contracts` so a caller can catch any security
failure without knowing which context raised it.

Each failure mode is a distinct type so a negative control can assert the
*reason* an action was refused. A control asserting only that something raised
would pass for an unrelated reason - the F-0017 defect.

None of these may be caught and converted into a permissive decision.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import GovernanceStateError
from arkali.kernel.contracts.security_errors import SecurityError


class PolicyDenied(SecurityError):
    """The PDP resolved the request to DENY."""

    code = "ARK-ERR-0031"


class UnknownOperationClass(SecurityError):
    """The action maps to no canonical operation class.

    `unmapped_action_resolution: DENY` — an unmappable action is refused, never
    passed through as unclassified.
    """

    code = "ARK-ERR-0032"


class MalformedPolicyState(GovernanceStateError):
    """Policy input is missing, malformed or self-contradictory. Fails closed.

    Derives from `GovernanceStateError` rather than `SecurityError`: a malformed
    policy input is a governance-state defect, and the checker must fail closed
    on it the same way it does for any other unreadable governed state.
    """

    code = "ARK-ERR-0033"


class ProtectedCoreMutation(SecurityError):
    """Direct mutation of a Protected Core context was attempted."""

    code = "ARK-ERR-0036"


class SecretAccessDenied(SecurityError):
    """A secret was requested outside a pre-authorized scope, or without a vault."""

    code = "ARK-ERR-0037"


class RawSecretLeak(SecurityError):
    """A raw secret value reached a path that may only carry references."""

    code = "ARK-ERR-0038"


class PolicyBypassAttempt(SecurityError):
    """A governed operation was attempted without a policy decision."""

    code = "ARK-ERR-0040"


class HumanGateNotRecorded(SecurityError):
    """An action requiring a human gate has no recorded decision."""

    code = "ARK-ERR-0041"
