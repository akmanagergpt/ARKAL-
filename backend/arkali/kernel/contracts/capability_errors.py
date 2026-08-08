"""Capability-graph failure taxonomy (Phase 3, ARK-REQ-0045 / ARK-REQ-0049).

Owner: kernel.contracts. Extends the C-01 taxonomy in `errors.py`; kept in a
sibling module for the same budget reason as `state_machine_errors` (ADR-0008).

No error here may be caught and converted into a PASS. In particular
`PrematureActivation` must never be downgraded to a NOT_CONFIGURED answer: the
first means "you asked too early", the second means "the authorities do not
exist yet", and conflating them would hide a phase-order violation.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import ContractViolation


class CapabilityError(ContractViolation):
    """Base of the capability-graph failure taxonomy."""

    code = "ARK-ERR-0018"


class MalformedCapabilityIdentity(CapabilityError):
    """A capability identifier or node field does not satisfy its declared form."""

    code = "ARK-ERR-0019"


class DuplicateCapabilityIdentity(CapabilityError):
    """Two nodes in one graph claim the same capability identity."""

    code = "ARK-ERR-0020"


class InvalidCapabilityReference(CapabilityError):
    """A reference points at a capability or authority that does not resolve."""

    code = "ARK-ERR-0021"


class ShadowRegistryViolation(CapabilityError):
    """A node stores a value owned by another authority instead of a reference.

    ADR-0001 and `AUTHORITY_MAP.yaml` `provider_authority` make the
    Provider/Model Registry the sole store of provider identity, model identity,
    configuration, health, availability, cost metadata and fallback
    configuration.
    """

    code = "ARK-ERR-0022"


class PrematureActivation(CapabilityError):
    """Activation or resolution was attempted before the phase that owns it.

    ADR-0003: schema at Phase 3, activation at Phase 9B.
    """

    code = "ARK-ERR-0023"
