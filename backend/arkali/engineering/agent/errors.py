"""C-22 / C-23 harness failure taxonomy.

Owner: `engineering.agent`.

WHY THESE ARE NOT IN `kernel.contracts`. Same reason as the C-11, C-12, C-14,
C-15, C-19 and C-21 taxonomies before them, and it was MEASURED here rather than
assumed: placing them there took `kernel.contracts` public surface to 42 against
a `max_public_surface_per_context` budget of 40, and the architecture gate
refused it. ADR-0008 makes decomposition the answer to a budget rather than an
exception, and an exception would in any case require HUMAN GATE 8 plus an ADR
and may not be authored by the implementing actor. `ContractViolation` is
imported from `kernel.contracts.contract_violation_base` (the PRE-PHASE-14
decomposition of `error_base.py`, which needed the same repair `errors.py`
got before it), so this context adds no edge to either hub module.

Each failure mode is a distinct type so a negative control can assert the
*reason* something was refused. A control asserting only that an exception was
raised would pass for an unrelated reason - the F-0017 defect.

NO ELEMENT LIST HERE, AND NO POLICY VERDICT. These types say what went wrong;
they do not say what the harness elements are (`harness_elements.py` parses that
from the canonical documents) and they never carry a permission decision, which
`control.policy` owns.

Codes are allocated from 0092 upward; 0088-0091 belong to
`control.registry.provider`.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class HarnessError(ContractViolation):
    """Base of the harness-task failure taxonomy."""

    code = "ARK-ERR-0092"


class UnboundedHarnessTask(HarnessError):
    """A task does not carry every canonical harness element.

    Never downgrade this to "a task with defaults supplied". `ARK-REQ-0231`
    means a task missing one of the canonical elements is not a bounded task at
    all, and filling the gap in would be the fabricated-value failure the Master
    Specification forbids.
    """

    code = "ARK-ERR-0093"


class MalformedHarnessElement(HarnessError):
    """An element is present but does not satisfy its declared form."""

    code = "ARK-ERR-0094"
