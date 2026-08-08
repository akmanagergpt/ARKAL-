"""Provider Health state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: control.registry.provider — AUTHORITY_MAP.yaml
`state_machine_authorities.ProviderHealth`.

This machine is the **only** store of provider health (§5 invariant, ADR-0001).
`control.capability` holds a reference and never a copy; that separation is
enforced structurally by the capability node schema, which has no health field
at all, and by the reference-not-copy validation in
`arkali.control.capability.capability_node`.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §5 is the canonical specification. The two are
reconciled by `backend/tests/state_machines/test_canonical_reconciliation.py`.

This machine has no terminal state, and that is correct rather than an omission:
a provider may always be re-enabled via DISABLED → CONFIGURED.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import StateMachine, StateMachineDefinition

MACHINE = "ProviderHealth"
AUTHORITY = "control.registry.provider"
SOURCE = "docs/canonical/STATE_MACHINES.md §5 Provider Health"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "UNCONFIGURED",
        "CONFIGURED",
        "HEALTHY",
        "DEGRADED",
        "UNHEALTHY",
        "DISABLED",
    ),
    transitions=(
        ("UNCONFIGURED", "CONFIGURED"),
        ("CONFIGURED", "HEALTHY"),
        ("CONFIGURED", "UNHEALTHY"),
        ("HEALTHY", "DEGRADED"),
        ("DEGRADED", "HEALTHY"),
        ("DEGRADED", "UNHEALTHY"),
        ("UNHEALTHY", "DEGRADED"),
        ("UNCONFIGURED", "DISABLED"),
        ("CONFIGURED", "DISABLED"),
        ("HEALTHY", "DISABLED"),
        ("DEGRADED", "DISABLED"),
        ("UNHEALTHY", "DISABLED"),
        ("DISABLED", "CONFIGURED"),
    ),
    forbidden=(),
    terminal=(),
)


def build() -> StateMachine:
    """The Provider Health machine. §5 declares no conditional transition."""
    return StateMachine(DEFINITION)
