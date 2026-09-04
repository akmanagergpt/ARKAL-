"""Composes a real, activated capability answer from real local-AI probes.

Owner: engineering.localai.

REUSE, NOT A SECOND AUTHORITY. Every piece composed here already exists and
is unchanged: `LocalRuntimeAdapter.probe`/`list_models` (the real runtime
probe), `evaluate_suitability` (the real hardware-aware verdict),
`build_capability_node` (the real C-13 node, `capability_exposure.py`),
`CapabilityGraph`/`ReferenceResolvers` (the real Phase 9B activated-query
mechanism, `control.capability`), `RequirementRegister`/`GovernanceState`
(the real governed activation-phase fact). This module's only job is
composition-root wiring: probe once, build the real graph, and hand back
(a) its `can_perform` bound method as `ProductionFactory`'s
`capability_query`, and (b) the id of a genuinely configured capability if
one exists — never a UI-supplied or hard-coded model name
(ARKALI COMMAND CENTER — DEF-009 FLOW A CONVERGENCE AUTHORIZATION, item 3).

ACTIVATION IS A REAL, GOVERNED FACT, NEVER A LOCAL CONSTANT — BUT READ BY
THE CALLER, NOT HERE. `ARK-REQ-0048` carries the Capability Graph's
activation phase in the register (`test_phase_9b_journey.py` step 1); this
module reads `activation_phase` from `RequirementRegister`
(`control.specification`) itself, but takes `current_phase` as a parameter
rather than asking `acceptance.engine`'s `GovernanceState` for it directly.
`engineering.localai` is a lower architecture layer than `acceptance.engine`
(`AUTHORITY_MAP.yaml`), and `acceptance.engine` is Protected Core; importing
it from here would both invert that layering and extend the repository's
longest dependency chain past `max_orchestration_depth` (proven by trying
it and running the real gate, not assumed). The composition root —
`scripts/run_command_center.py`, itself outside the measured architecture
graph — resolves the real governed fact and passes it in.
`CapabilityGraph.is_activated` is `current_phase == activation_phase` by
construction (ADR-0003): "between those phases every query returns
NOT_CONFIGURED" reads as "and not after them" once 9B is genuinely
reached, so a real caller sets `current_phase` to the SAME governed value
as `activation_phase` exactly when phase 9B is `MACHINE-ACCEPTED`.

NO CAPABILITY IS FABRICATED. A model answers PASS only when a real,
bounded, timed-out probe against the real runtime and a real,
hardware-aware suitability verdict both genuinely resolved PASS on THIS
host, right now — the same two-condition rule `build_capability_node`
already enforces. If no local runtime answers, or no model fits, the graph
declares no node for it at all and the real caller sees the honest refusal.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from arkali.control.capability.capability_graph import (
    CapabilityGraph,
    CapabilityQueryResult,
)
from arkali.control.capability.capability_node import CapabilityNode
from arkali.control.capability.reference_authority import (
    CapabilityReferenceAuthority,
)
from arkali.control.capability.reference_resolution import ReferenceResolvers
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.localai.adapter import HonestState, LocalRuntimeAdapter
from arkali.engineering.localai.capability_exposure import build_capability_node
from arkali.engineering.localai.host_probe import probe_host
from arkali.engineering.localai.suitability import evaluate_suitability

#: `ARK-REQ-0048` is where the register carries the Capability Graph's own
#: activation phase (`docs/canonical/REQUIREMENT_REGISTER.md`).
_ACTIVATION_REQUIREMENT: str = "ARK-REQ-0048"


class RealCapabilityAuthority(BaseModel):
    """The one-time result of probing a real local runtime.

    `query` is the same shape `ProductionFactory`'s `capability_query`
    already expects. `default_capability_id` is `None` unless a real probe
    and a real, hardware-aware suitability verdict both genuinely resolved
    PASS for at least one model — a fact this authority derived, never a
    caller's guess.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    query: Callable[[str], CapabilityQueryResult]
    default_capability_id: str | None


def _probe_nodes(
    adapter: LocalRuntimeAdapter,
) -> tuple[CapabilityNode, ...]:
    probe = adapter.probe()
    if probe.state is not HonestState.PASS:
        return ()
    host = probe_host()
    return tuple(
        build_capability_node(descriptor, probe, evaluate_suitability(descriptor, host))
        for descriptor in adapter.list_models()
    )


def compose_real_capability_authority(
    repo_root: pathlib.Path, adapter: LocalRuntimeAdapter, current_phase: str,
) -> RealCapabilityAuthority:
    """Probe `adapter` exactly once and compose the real, activated authority.

    A bounded, read-only probe — the same one every `LocalRuntimeAdapter`
    caller already performs — run once at composition time, not per
    request: the real `CapabilityGraph.can_perform` still re-derives its
    verdict from the frozen node set on every call (ADR-0003's
    no-cached-verdict rule), but nothing about a model's own
    configured/unconfigured state is re-probed per HTTP request.

    `current_phase`: the caller's own real, governed answer to "has phase
    9B been reached" — see this module's own docstring for why it is not
    derived in here.
    """
    register = RequirementRegister.load(repo_root)
    activation_phase = register.get(_ACTIVATION_REQUIREMENT).owning_phase

    nodes = _probe_nodes(adapter)
    references = ReferenceResolvers(CapabilityReferenceAuthority.load(repo_root), {})
    graph = CapabilityGraph(
        nodes,
        activation_phase=activation_phase,
        current_phase=current_phase,
        references=references,
    )
    # Asked through the real graph, not read off `node.configured_state`
    # directly: a node can be genuinely CONFIGURED and the graph still
    # pre-activation, and the default offered here must match what a real
    # query would actually answer, never a node fact the activation gate
    # would itself refuse.
    configured = next(
        (node.id for node in nodes if graph.can_perform(node.id).state is HonestState.PASS),
        None,
    )
    return RealCapabilityAuthority(query=graph.can_perform, default_capability_id=configured)


__all__ = ["RealCapabilityAuthority", "compose_real_capability_authority"]
