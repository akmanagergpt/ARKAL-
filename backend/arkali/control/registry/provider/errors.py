"""C-11 provider/model record error types.

Owner: `control.registry.provider`.

WHY THESE ARE NOT IN `kernel.contracts.errors`. Same reason as the C-11, C-12,
C-14, C-15, C-19 and C-21 taxonomies before them: that module sits at its
`max_fan_in_per_module` budget of 15, and ADR-0008 makes decomposition the
answer to a budget rather than an exception. The abstract base layer lives in
`kernel.contracts.error_base` (F-0042's decomposition) and is imported from
there, so this context adds no edge to `errors.py`.

Each failure mode is a distinct type so a negative control can assert the
*reason* something was refused. A control asserting only that an exception was
raised would pass for an unrelated reason - the F-0017 defect.

NO HEALTH ERRORS HERE. An illegal provider-health move is refused by the
canonical `ProviderHealth` machine and raises the machine's own typed error,
unchanged. Re-raising it as a registry error would make this context look like a
second health authority, which is exactly what ARK-REQ-0052 forbids.

Codes are allocated from 0088 upward; 0081-0087 belong to `execution.scheduler`.
"""

from __future__ import annotations

from arkali.kernel.contracts.error_base import ContractViolation


class InvalidProviderIdentity(ContractViolation):
    """A provider or model identity is empty, malformed or duplicated.

    Identity is one of the seven concerns ARK-REQ-0052 assigns to this registry,
    so a record whose identity cannot be trusted is refused rather than stored.
    """

    code = "ARK-ERR-0088"


class RawSecretInProviderConfiguration(ContractViolation):
    """Provider configuration carries something shaped like a raw secret.

    ARK-REQ-0100 forbids any automated actor writing, reading or exporting a raw
    secret, and C-09 makes the boundary a type with nowhere to put one. The
    registry owns provider *configuration*, which in practice is where an API key
    would be smuggled in, so the refusal lives here rather than in a convention.
    """

    code = "ARK-ERR-0089"


class ForeignProviderConcern(ContractViolation):
    """A record declares a concern the canonical authority does not assign here.

    The seven owned concerns are governed data in `AUTHORITY_MAP.yaml`
    `provider_authority.fields_owned`. A record carrying an eighth would make
    this registry the authority for something nobody granted it.
    """

    code = "ARK-ERR-0090"


class UnknownProviderHealthState(ContractViolation):
    """A record declares a health state the canonical machine does not define.

    The state vocabulary belongs to the `ProviderHealth` machine delivered at
    Phase 3. This registry reads it and never restates it, so an unrecognised
    state is refused instead of being admitted as a new one.
    """

    code = "ARK-ERR-0091"
