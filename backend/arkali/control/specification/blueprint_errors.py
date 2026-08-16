"""Typed C-37 blueprint-contract failures owned by ``control.specification``.

Imports `ContractViolation` from `contract_violation_base`, not `errors`:
`kernel.contracts.errors` measures fan-in per importing FILE, and
`register_parser.py` already holds control.specification's one edge into it
(measured at fan-in 15 of 15). `contract_violation_base.py` exists precisely
to absorb a further importer without re-opening that ceiling — the same
seam Phase 14's `engineering/repair/errors.py` uses.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class MalformedProductGoalError(ContractViolation):
    """A submitted product goal carries no usable content to derive from.

    Raised only for structurally empty/unusable input (D-025 responsibility 1).
    Content-level ambiguity, contradiction and underspecification are never
    raised — ARK-REQ-0383 requires them recorded as unresolved governed
    questions on the blueprint itself, not as a refusal to produce one.
    """

    code = "ARK-ERR-0113"
