"""C-36 child-product evolution campaign: composes the real, unmodified C-33
machinery MS "AI-Native Child Products" names, never a second one
(ARK-REQ-0132, ARK-REQ-0133).

Owner: `lifecycle.evolution`.

NO NEW STATE MACHINE. MS states plainly: "Product Evolution SDK improvement
cycles use the same bounded campaign model, budgets and terminal states as
ARKALI Self-Evolution." `evolution_campaign_state_machine.build()` -
`EvolutionCampaign`, `STATE_MACHINES.md` §10 - is imported and called
directly here, unmodified; this module mints no `StateMachineDefinition` of
its own. `STATE_MACHINES.md` stays at twelve authorities and
`lifecycle.evolution` gains no second `state_machine_authorities` entry -
a child-product campaign is a new *instance* of the existing machine, the
same way a second workflow execution is a new instance of `WorkflowExecution`
rather than a second machine.

NO SECOND CAMPAIGN AUTHORITY. `CampaignDeclaration`/`CampaignBudgets`
(`campaign_declaration.py`) are reused by direct import, not copied or
reimplemented; their own fields already carry no ARKALI-core-specific
concept, so nothing about them needed to change for a child-product subject.
The only thing this module adds is *which* subject a campaign evolves - a
child product's identity - encoded into the declaration's own
free-form `campaign_id`, never a new field on the reused type.

MODE ELIGIBILITY IS ENFORCED, NOT ASSUMED. MS reserves the SDK for
`AI_NATIVE_SELF_EVOLVING` products only (`child_product_identity.py`).
`declare_child_product_campaign` refuses before constructing anything for a
`STANDARD` or `AI_ASSISTED` identity - a caller cannot manufacture a
declaration that bypasses the check because the check runs before the
declaration exists, not after.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from arkali.lifecycle.evolution import evolution_campaign_state_machine as ecsm
from arkali.lifecycle.evolution.campaign_declaration import (
    CampaignBudgets,
    CampaignDeclaration,
)
from arkali.lifecycle.evolution.child_product_identity import ChildProductIdentity
from arkali.lifecycle.evolution.content_identity import address_of

# Re-exported from `core_upgrade_state_machine`, already a counted
# `kernel.contracts.state_machine` importer, rather than importing this
# context's own kernel type a second time - `kernel.contracts.state_machine`
# was already at its fan-in ceiling (15 of 15) before this module.
from arkali.lifecycle.evolution.core_upgrade_state_machine import StateMachineInstance
from arkali.lifecycle.evolution.errors import ChildProductNotSdkEligibleError

#: The one declared state `EvolutionCampaign` has no incoming transition
#: from - derived from the machine, never hard-coded (mirrors
#: `core_upgrade_orchestrator._initial_state`).
_DECLARED: Final[str] = "DECLARED"
_RUNNING: Final[str] = "RUNNING"
#: Prefix binding a campaign's free-form `campaign_id` to the child product
#: it evolves, so the subject is recoverable from the declaration alone
#: without a second lookup table.
_CAMPAIGN_ID_PREFIX: Final[str] = "child-product"


def _child_campaign_id(identity: ChildProductIdentity, objective: str) -> str:
    """The deterministic `campaign_id` for one product's one evolution
    request - content-addressed over both, never a caller-chosen free
    string. Binding to `objective` as well as `product_ref` (not the
    product alone) is deliberate and was a real defect found by running
    `test_child_product_journey.py`: a child product receives more than one
    evolution request over its lifetime, and each is its own campaign, not
    a shared namespace one product's every campaign would otherwise
    collide into - the second request's workspace allocation genuinely
    failed as "already allocated" against the first's before this fix."""
    payload = f"{identity.product_ref}:{objective}".encode()
    return f"{_CAMPAIGN_ID_PREFIX}:{address_of(payload)}"


def declare_child_product_campaign(
    identity: ChildProductIdentity,
    *,
    objective: str,
    baseline_metrics: Mapping[str, float],
    budgets: CampaignBudgets,
) -> CampaignDeclaration:
    """ARK-REQ-0132/0133: declare one child product's evolution campaign
    using the real, unmodified C-33 `CampaignDeclaration` - never a
    hand-built dict skipping real typed budgets.

    Raises `ChildProductNotSdkEligibleError` for a `STANDARD`/`AI_ASSISTED`
    identity before anything is constructed.
    """
    if not identity.uses_evolution_sdk:
        raise ChildProductNotSdkEligibleError(
            f"child product {identity.product_id!r} is mode "
            f"{identity.mode.value!r}; only AI_NATIVE_SELF_EVOLVING products "
            "are eligible for the Product Evolution SDK"
        )
    return CampaignDeclaration(
        campaign_id=_child_campaign_id(identity, objective),
        objective=objective,
        baseline_metrics=baseline_metrics,
        budgets=budgets,
    )


def begin_child_product_campaign(
    declaration: CampaignDeclaration,
) -> StateMachineInstance:
    """The only production path from a child-product declaration to a
    `RUNNING` `EvolutionCampaign` instance - the real, unmodified machine
    Phase 23 already built, satisfied only through the declaration's own
    `guard_context()` (ARK-REQ-0139's guard, reused, not reimplemented)."""
    instance = ecsm.build().start(_DECLARED)
    instance.apply(_RUNNING, declaration.guard_context())
    return instance
