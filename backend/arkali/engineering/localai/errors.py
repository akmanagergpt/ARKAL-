"""Typed `engineering.localai` errors.

Imports `ContractViolation` from `contract_violation_base`, not `error_base`
(fan-in 15 of 15) - the ADR-0008 absorber module every later context needing
only the contract-violation base already imports, the same choice
`engineering.plugin` and `engineering.import` recorded first.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class LocalRuntimeTargetNotLoopbackError(ContractViolation):
    """A local-AI adapter declared or attempted a non-loopback endpoint.

    `engineering.localai` is a LOCAL runtime boundary: MS §Local-Only mode
    requires that local AI, local execution and all local capabilities remain
    available while every outbound network egress is DENY. An adapter whose
    declared endpoint is not loopback cannot honestly claim to be "local", so
    construction refuses rather than producing an adapter that would need a
    policy check to catch the same defect later (ARK-REQ-0016, ARK-REQ-0129).
    """

    code = "ARK-ERR-0149"


class MalformedLocalModelDescriptorError(ContractViolation):
    """A local model descriptor could not have described a real local model."""

    code = "ARK-ERR-0150"
