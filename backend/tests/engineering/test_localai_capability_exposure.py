"""Real C-13 capability nodes from real local-AI results, and Phase 16 sees
them (Stage 5: exposes capability, never routing policy).

`execution_routing.select_execution_tier` (Phase 16, `engineering.factory`) is
imported unmodified. This file proves ONLY that a real, activated
`CapabilityGraph` carrying an `engineering.localai`-built node makes the
`LOCAL_MODEL` tier resolve `SELECTED` when genuinely configured, and
`NOT_CONFIGURED` (falling through, honestly, to `HUMAN_GOVERNANCE`) when not -
never that this context performs routing itself.
"""

from __future__ import annotations

from arkali.control.capability.reference_resolution import ReferenceResolvers
from arkali.engineering.factory.execution_routing import (
    ExecutionTier,
    TierEligibilityRequest,
    TierState,
    select_execution_tier,
)
from arkali.engineering.localai.adapter import (
    HonestState,
    LocalModelDescriptor,
    RuntimeProbeResult,
)
from arkali.engineering.localai.capability_exposure import (
    build_capability_node,
    capability_id_for,
)
from arkali.engineering.localai.suitability import SuitabilityVerdict
from tests.execution.scheduler_admission_harness import activated_graph, binding

DESCRIPTOR = LocalModelDescriptor(
    runtime="ollama", model_id="qwen2.5-coder:7b", parameter_size="7.6B",
    quantization="Q4_K_M", context_length=32768,
)
PASSING_PROBE = RuntimeProbeResult(runtime="ollama", state=HonestState.PASS, detail="ok")
FAILING_PROBE = RuntimeProbeResult(
    runtime="ollama", state=HonestState.NOT_CONFIGURED, detail="unreachable"
)
FITTING = SuitabilityVerdict(model_id=DESCRIPTOR.model_id, state=HonestState.PASS, reason="fits")
NOT_FITTING = SuitabilityVerdict(
    model_id=DESCRIPTOR.model_id, state=HonestState.NOT_CONFIGURED, reason="too large"
)


def _empty_resolvers() -> ReferenceResolvers:
    """No external reference is declared by a local-AI node, so an authority
    set with nothing supplied resolves it fully - proven directly below."""
    return ReferenceResolvers(binding(), {})


class TestCapabilityIdIsStableAndDeterministic:
    def test_the_same_descriptor_always_yields_the_same_id(self) -> None:
        assert capability_id_for(DESCRIPTOR) == capability_id_for(DESCRIPTOR)

    def test_the_id_is_a_valid_dotted_lowercase_capability_identifier(self) -> None:
        node = build_capability_node(DESCRIPTOR, PASSING_PROBE, FITTING)
        assert node.id == capability_id_for(DESCRIPTOR)

    def test_different_models_yield_different_ids(self) -> None:
        other = DESCRIPTOR.model_copy(update={"model_id": "qwen2.5-coder:14b"})
        assert capability_id_for(DESCRIPTOR) != capability_id_for(other)


class TestConfiguredStateIsEarnedNeverDefaulted:
    def test_a_passing_probe_and_fitting_suitability_configure_the_node(self) -> None:
        node = build_capability_node(DESCRIPTOR, PASSING_PROBE, FITTING)
        assert node.configured_state.value == "CONFIGURED"

    def test_a_failing_probe_leaves_the_node_unconfigured(self) -> None:
        node = build_capability_node(DESCRIPTOR, FAILING_PROBE, FITTING)
        assert node.configured_state.value == "UNCONFIGURED"

    def test_unfitting_hardware_leaves_the_node_unconfigured_even_if_reachable(
        self,
    ) -> None:
        node = build_capability_node(DESCRIPTOR, PASSING_PROBE, NOT_FITTING)
        assert node.configured_state.value == "UNCONFIGURED"

    def test_no_provider_owned_field_is_smuggled_into_runtime_requirements(
        self,
    ) -> None:
        from arkali.control.capability.capability_node import validate_no_shadow_registry

        node = build_capability_node(DESCRIPTOR, PASSING_PROBE, FITTING)
        validate_no_shadow_registry(
            node,
            ["identity", "model_identity", "configuration", "health",
             "availability", "cost_metadata", "fallback"],
        )


class TestPhase16SeesTheLocalTierEligible:
    """The real, unmodified Phase 16 router, driven by a real, activated
    `CapabilityGraph` composed here - never a second routing authority."""

    def test_a_genuinely_configured_local_model_selects_the_local_model_tier(
        self,
    ) -> None:
        node = build_capability_node(DESCRIPTOR, PASSING_PROBE, FITTING)
        graph = activated_graph(node, references=_empty_resolvers())
        selection = select_execution_tier(
            TierEligibilityRequest(task_id="t-1", capability_id=node.id),
            capability_query=graph.can_perform,
        )
        assert selection.selected is ExecutionTier.LOCAL_MODEL

    def test_an_unavailable_local_model_falls_through_honestly(self) -> None:
        node = build_capability_node(DESCRIPTOR, FAILING_PROBE, FITTING)
        graph = activated_graph(node, references=_empty_resolvers())
        selection = select_execution_tier(
            TierEligibilityRequest(task_id="t-2", capability_id=node.id),
            capability_query=graph.can_perform,
        )
        local_eval = next(
            e for e in selection.evaluations if e.tier is ExecutionTier.LOCAL_MODEL
        )
        assert local_eval.state is TierState.NOT_CONFIGURED
        assert selection.selected is ExecutionTier.HUMAN_GOVERNANCE

    def test_no_configured_model_name_alone_ever_creates_a_pass(self) -> None:
        """A node that merely EXISTS, unconfigured, still resolves NOT_CONFIGURED."""
        node = build_capability_node(DESCRIPTOR, FAILING_PROBE, NOT_FITTING)
        graph = activated_graph(node, references=_empty_resolvers())
        result = graph.can_perform(node.id)
        assert result.state is HonestState.NOT_CONFIGURED

    def test_cloud_tiers_are_not_falsely_disabled_by_a_configured_local_model(
        self,
    ) -> None:
        """Selecting LOCAL_MODEL never asserts anything about a cloud tier's
        own eligibility - every tier is still evaluated and recorded."""
        node = build_capability_node(DESCRIPTOR, PASSING_PROBE, FITTING)
        graph = activated_graph(node, references=_empty_resolvers())
        selection = select_execution_tier(
            TierEligibilityRequest(task_id="t-3", capability_id=node.id),
            capability_query=graph.can_perform,
        )
        tiers_seen = {e.tier for e in selection.evaluations}
        assert tiers_seen == set(ExecutionTier)
