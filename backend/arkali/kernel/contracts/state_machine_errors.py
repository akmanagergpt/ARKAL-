"""State-machine failure taxonomy (Phase 3, ARK-REQ-0043 / ARK-REQ-0044).

Owner: kernel.contracts. Extends the C-01 taxonomy in `errors.py`; kept in a
sibling module because the combined taxonomy exceeds
`max_public_symbols_per_module`, and decomposition is the intended response to a
numeric budget (ADR-0008).

Each failure mode is a distinct type so a negative control can assert the
*reason* a transition was rejected. A control that only asserts "something was
raised" would pass for an unrelated reason - the defect recorded as F-0017.

No error here may be caught and converted into a PASS.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import ContractViolation


class StateMachineError(ContractViolation):
    """Base of the state-machine failure taxonomy."""

    code = "ARK-ERR-0010"


class UnknownState(StateMachineError):
    """A state identifier is not a member of the machine's declared states.

    Also raised for malformed input - a non-string or blank identifier is not a
    state, and must not be coerced into one.
    """

    code = "ARK-ERR-0011"


class IllegalTransition(StateMachineError):
    """The transition is not in the machine's declared transition relation."""

    code = "ARK-ERR-0012"


class ForbiddenTransition(IllegalTransition):
    """The transition is explicitly enumerated as forbidden.

    A subtype of `IllegalTransition`: every forbidden transition is illegal, but
    the canonical inventory names some explicitly (`CREATED→PROMOTED`) and those
    must stay distinguishable in evidence.
    """

    code = "ARK-ERR-0013"


class TerminalStateEscape(IllegalTransition):
    """An outgoing transition was attempted from a terminal state."""

    code = "ARK-ERR-0014"


class GuardRejected(StateMachineError):
    """A declared guard evaluated false for this transition."""

    code = "ARK-ERR-0015"


class StateMutationBypass(StateMachineError):
    """Direct mutation of machine state was attempted, bypassing the rules."""

    code = "ARK-ERR-0016"


class StateMachineDefinitionError(StateMachineError):
    """A machine definition is internally contradictory. Raised at construction.

    A contradictory machine therefore cannot exist, rather than existing and
    being reported later.
    """

    code = "ARK-ERR-0017"
