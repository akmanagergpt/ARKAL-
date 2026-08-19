"""C-09 secret reference / Permission Broker boundary (ARK-REQ-0098 … 0103).

Owner: control.policy (Protected Core).

THIS MODULE CANNOT HOLD A SECRET. `SecretReference` has no field capable of
carrying a raw value, and the broker never returns one. That is the boundary:
not a rule that raw values should not be passed around, but a type that has
nowhere to put one. Raw values therefore cannot reach a log, prompt, context
package, export, release artifact or evidence record through this path, because
they never enter it.

Provisioning is deliberately absent. Secrets enter the vault only through
explicit human-initiated provisioning (ARK-REQ-0099); no automated actor may
write, read or export a raw secret (ARK-REQ-0100). There is consequently no
`store()` function here for an agent to call - the capability an automated actor
would need simply does not exist in this contract.

OS KEY PROTECTION IS NOT ASSUMED (ARK-REQ-0102, 0103). The broker is constructed
with the probed availability of an OS key-protection facility. Without it,
secret-dependent capabilities are UNSUPPORTED rather than stored unprotected -
the vault refuses to broker rather than degrading to a weaker store.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.results import HonestState
from arkali.control.policy.policy_errors import (
    RawSecretLeak,
    SecretAccessDenied,
)

#: Patterns that indicate a raw secret rather than a reference. Used to prove the
#: boundary holds, never to sanitise a value into acceptability.
_RAW_SECRET_SHAPES = re.compile(
    r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9]{16,}|"
    r"\bghp_[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{16}\b)"
)


class SecretReference(BaseModel):
    """A scoped, revocable handle. Carries no secret value, by construction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    handle: str
    scope: str
    revoked: bool = False

    def __str__(self) -> str:
        """Rendering a reference must never look like a value."""
        return f"<secret-ref {self.handle} scope={self.scope}>"

    @property
    def is_usable(self) -> bool:
        return not self.revoked


class PermissionBroker:
    """Issues scoped references. Never issues, stores or returns a raw value."""

    def __init__(self, key_protection: HonestState, facility: str = "") -> None:
        self.key_protection = key_protection
        self.facility = facility
        self._issued: dict[str, SecretReference] = {}

    @property
    def is_operational(self) -> bool:
        """Only a probed PASS enables brokering. NOT_TESTED is not availability."""
        return self.key_protection is HonestState.PASS

    @property
    def capability_state(self) -> HonestState:
        """ARK-REQ-0103: no OS key protection ⇒ UNSUPPORTED, never degraded."""
        return HonestState.PASS if self.is_operational else HonestState.UNSUPPORTED

    def issue(self, handle: str, scope: str, *, authorized_scopes: tuple[str, ...]
              ) -> SecretReference:
        """Issue a reference, only within a pre-authorized scope."""
        if not self.is_operational:
            raise SecretAccessDenied(
                f"no OS key-protection facility available "
                f"({self.key_protection.value}); secret-dependent capabilities "
                f"are {self.capability_state.value} rather than stored unprotected"
            )
        if not handle.strip() or not scope.strip():
            raise SecretAccessDenied("a reference requires a handle and a scope")
        if scope not in authorized_scopes:
            raise SecretAccessDenied(
                f"scope {scope!r} is not pre-authorized; ACCESS_SECRET is never "
                "AUTO outside a pre-authorized scope"
            )
        reference = SecretReference(handle=handle, scope=scope)
        self._issued[handle] = reference
        return reference

    def revoke(self, handle: str) -> SecretReference:
        reference = self._issued.get(handle)
        if reference is None:
            raise SecretAccessDenied(f"unknown secret handle {handle!r}")
        revoked = reference.model_copy(update={"revoked": True})
        self._issued[handle] = revoked
        return revoked

    def resolve(self, reference: SecretReference) -> str:
        """Deliberately refuses. No caller may obtain a raw value through here."""
        raise RawSecretLeak(
            f"{reference} cannot be resolved to a raw value through the broker; "
            "consumers receive scoped references only. Raw resolution belongs to "
            "the vault's OS-protected boundary, which is not exposed to callers."
        )


def assert_no_raw_secret(payload: str, *, sink: str) -> None:
    """Guard for any path that may only carry references.

    Used on evidence, log, prompt and export paths. It reports the sink so a
    negative control can assert *which* boundary refused, rather than that
    something somewhere raised.
    """
    found = _RAW_SECRET_SHAPES.search(payload)
    if found is not None:
        raise RawSecretLeak(
            f"raw secret material reached {sink}; this path may carry scoped "
            f"references only (matched {found.group(0)[:12]}...)"
        )


#: The token a redacted match is replaced with. Never a partial mask (a
#: truncated key can still be a working credential) - the whole match is
#: removed, always.
REDACTED_TOKEN = "[REDACTED-SECRET]"


def redact_raw_secrets(payload: str) -> str:
    """Replace every raw-secret-shaped match with `REDACTED_TOKEN`.

    Reuses `_RAW_SECRET_SHAPES` - the identical pattern `assert_no_raw_secret`
    already enforces - so an export path (ARK-REQ-0169/0357: "Source
    Intelligence Export and AI Review Bundle... secrets redacted") and the
    hard-refusal path can never independently drift on what counts as a
    secret shape. Redaction is additive to, never a replacement for,
    `assert_no_raw_secret`: a caller that must refuse rather than mask still
    calls that function; this one is for a caller whose whole point is to
    produce readable output with the secret shape removed.
    """
    return _RAW_SECRET_SHAPES.sub(REDACTED_TOKEN, payload)
