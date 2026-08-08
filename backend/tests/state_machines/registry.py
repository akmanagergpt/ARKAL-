"""Test-tier registry of the twelve canonical machines.

This module deliberately lives in the test tier, not in `backend/arkali`. The
twelve definitions are owned by ten different bounded contexts spanning layer
ranks 1 to 5; any production module importing all of them would violate
`allow_same_layer: false` and `allow_higher_layer: false`, and would exceed
`max_contexts_touched_by_module: 3`. Tests sit outside the context graph, so the
reconciliation can see every machine at once without creating an illegal edge.

It is a lookup, not an authority: it maps names to the modules that own them and
asserts nothing about states or transitions.
"""

from __future__ import annotations

from arkali.acceptance import hardening_round_state_machine
from arkali.control.registry.project import project_state_machine
from arkali.control.registry.provider import provider_health_state_machine
from arkali.engineering.candidate import candidate_state_machine
from arkali.engineering.plugin import plugin_lifecycle_state_machine
from arkali.engineering.project_import import import_project_state_machine
from arkali.execution.durable import job_state_machine
from arkali.execution.workflow import workflow_execution_state_machine
from arkali.kernel.contracts.state_machine import StateMachine
from arkali.lifecycle.evolution import (
    core_upgrade_state_machine,
    evolution_campaign_state_machine,
)
from arkali.lifecycle.recovery import backup_restore_state_machine
from arkali.lifecycle.release import release_state_machine

#: machine name -> its owning definition module.
MACHINE_MODULES = {
    "Project": project_state_machine,
    "Candidate": candidate_state_machine,
    "Job": job_state_machine,
    "WorkflowExecution": workflow_execution_state_machine,
    "ProviderHealth": provider_health_state_machine,
    "PluginLifecycle": plugin_lifecycle_state_machine,
    "Release": release_state_machine,
    "CoreUpgrade": core_upgrade_state_machine,
    "BackupRestore": backup_restore_state_machine,
    "EvolutionCampaign": evolution_campaign_state_machine,
    "HardeningRound": hardening_round_state_machine,
    "ImportProject": import_project_state_machine,
}


def all_machines() -> dict[str, StateMachine]:
    return {name: module.build() for name, module in MACHINE_MODULES.items()}
