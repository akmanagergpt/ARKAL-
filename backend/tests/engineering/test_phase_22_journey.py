"""The composed Phase 22 real-authority journey (Local AI + Model Laboratory).

Register denominator -> two structurally distinct, loopback-only adapters
proving no single-runtime dependency (ARK-REQ-0016) -> real host/runtime
probes, genuinely applicable on this host, feeding a hardware-aware
suitability verdict and one bounded, real local inference call
(ARK-REQ-0129) -> a real, activated CapabilityGraph carrying the resulting
node, proving Phase 16's unmodified execution_routing.select_execution_tier
resolves the local tier eligible -> the real PDP's Local-Only proof, loopback
permitted and an external target denied -> ARK-REQ-0130's honest
NOT_APPLICABLE, because no dataset-verification authority exists anywhere in
this repository.

No cloud AI provider is contacted anywhere in this journey. The one live
network call this journey makes targets 127.0.0.1 only (this host's own,
already-running Ollama server) - never an external host.
"""

from __future__ import annotations

import pathlib
from typing import Final

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.capability.reference_resolution import ReferenceResolvers
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.factory.execution_routing import (
    ExecutionTier,
    TierEligibilityRequest,
    select_execution_tier,
)
from arkali.engineering.localai.adapter import HonestState, LocalModelDescriptor
from arkali.engineering.localai.capability_exposure import build_capability_node
from arkali.engineering.localai.host_probe import (
    HostFacts,
    probe_accelerator,
    probe_host,
    probe_local_ai_runtime,
)
from arkali.engineering.localai.network_policy import gate_local_call
from arkali.engineering.localai.ollama_adapter import OllamaAdapter
from arkali.engineering.localai.openai_compatible_adapter import OpenAICompatibleAdapter
from arkali.engineering.localai.suitability import SuitabilityVerdict, evaluate_suitability

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE_ROOT: Final[pathlib.Path] = REPO / "backend/arkali/engineering/localai"

_MANDATORY_IDS: Final[frozenset[str]] = frozenset({"ARK-REQ-0016"})
_CONDITIONAL_IDS: Final[frozenset[str]] = frozenset({"ARK-REQ-0129", "ARK-REQ-0130"})

TRUST_TIER = "TRUST-1"
ACTOR = "engineering.localai"


def _best_fitting_model(
    models: tuple[LocalModelDescriptor, ...], host: HostFacts,
) -> tuple[LocalModelDescriptor, SuitabilityVerdict]:
    """The real, hardware-aware choice: the smallest model this host's RAM
    estimate judges PASS, not an arbitrary registry-order first entry."""
    evaluated = [(m, evaluate_suitability(m, host)) for m in models]
    fitting = [(m, v) for m, v in evaluated if v.state is HonestState.PASS]
    assert fitting, "no real installed model was judged suitable on this host"
    fitting.sort(key=lambda pair: pair[1].estimated_memory_bytes or 0)
    return fitting[0]


def test_step_0_no_cloud_ai_provider_is_contacted_anywhere_in_the_shipping_source() -> None:
    offenders = [
        f"{path.relative_to(REPO)}: {marker}"
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        for marker in ("openai.", "anthropic.", "import openai", "import anthropic")
        if marker in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"cloud provider marker present: {offenders}"


def test_step_1_the_real_register_denominator() -> None:
    register = RequirementRegister.load(REPO)
    phase22 = {r.req_id for r in register.for_phase("22")}
    assert phase22 == _MANDATORY_IDS | _CONDITIONAL_IDS

    by_id = {r.req_id: r for r in register.for_phase("22")}
    assert by_id["ARK-REQ-0016"].is_mandatory
    assert not by_id["ARK-REQ-0129"].is_mandatory
    assert not by_id["ARK-REQ-0130"].is_mandatory
    for req_id in phase22:
        assert by_id[req_id].owning_component == "engineering.localai"


def test_step_2_state_machine_count_stays_twelve() -> None:
    """This phase adds no new machine and claims no capability graph or
    provider registry of its own."""
    authority_map = AuthorityMap.load(REPO)
    assert len(authority_map.state_machine_authorities) == 12


class TestCondition0016NoSingleRuntimeDependency:
    """Two adapters, one Protocol, no shared transport - see also
    test_localai_adapter_architecture.py for the exhaustive structural proof;
    this cluster proves it composes into the phase journey."""

    def test_two_structurally_distinct_adapters_exist(self) -> None:
        assert OllamaAdapter().runtime != OpenAICompatibleAdapter().runtime

    def test_both_adapters_are_loopback_only_by_construction(self) -> None:
        assert OllamaAdapter().endpoint.startswith("http://127.0.0.1")
        assert OpenAICompatibleAdapter().endpoint.startswith("http://127.0.0.1")


class TestCondition0129HardwareAwareLocalAiOnThisRealHost:
    """This host's own real facts make ARK-REQ-0129 genuinely APPLICABLE
    (Appendix A: isolation.probe.local_ai_runtime_available AND
    hardware.probe.accelerator_present), so this cluster owes real
    integration evidence, not a NOT_APPLICABLE deferral."""

    def test_the_applicability_rule_is_genuinely_true_on_this_host(self) -> None:
        runtime_available = probe_local_ai_runtime(OllamaAdapter())
        accelerator_present, _ = probe_accelerator()
        assert runtime_available is True
        assert accelerator_present is True

    def test_a_real_installed_model_is_hardware_aware_suitable(self) -> None:
        host = probe_host()
        models = OllamaAdapter().list_models()
        assert models, "no real Ollama model found on this host"
        descriptor, verdict = _best_fitting_model(models, host)
        assert verdict.state is HonestState.PASS

    def test_the_verdict_is_unaffected_by_accelerator_presence(self) -> None:
        """Stage 6: never assume GPU support - the suitability decision is
        identical whether or not this host's real GPU is reported present."""
        host = probe_host()
        models = OllamaAdapter().list_models()
        descriptor, _ = _best_fitting_model(models, host)
        with_gpu = host.model_copy(update={"accelerator_present": True})
        without_gpu = host.model_copy(update={"accelerator_present": False})
        assert (
            evaluate_suitability(descriptor, with_gpu).state
            == evaluate_suitability(descriptor, without_gpu).state
        )

    def test_a_real_bounded_local_inference_call_genuinely_completes(self) -> None:
        host = probe_host()
        adapter = OllamaAdapter()
        models = adapter.list_models()
        assert models, "no real Ollama model found on this host"
        descriptor, _ = _best_fitting_model(models, host)
        result = adapter.infer(
            descriptor.model_id, "Reply with exactly one word: ready",
            timeout_seconds=60.0,
        )
        assert result.state is HonestState.PASS
        assert result.runtime == "ollama"
        assert result.elapsed_seconds > 0
        assert result.output_excerpt

    def test_phase_16_sees_the_real_local_model_as_an_eligible_tier(self) -> None:
        host = probe_host()
        adapter = OllamaAdapter()
        models = adapter.list_models()
        descriptor, suitability = _best_fitting_model(models, host)
        probe = adapter.probe()
        node = build_capability_node(descriptor, probe, suitability)

        from tests.execution.scheduler_admission_harness import activated_graph, binding

        graph = activated_graph(node, references=ReferenceResolvers(binding(), {}))
        selection = select_execution_tier(
            TierEligibilityRequest(task_id="phase-22-journey", capability_id=node.id),
            capability_query=graph.can_perform,
        )
        assert selection.selected is ExecutionTier.LOCAL_MODEL

    def test_the_adapters_never_import_control_policy_for_their_own_traffic(
        self,
    ) -> None:
        """Local AI's own loopback calls are never classified as
        NETWORK_EXTERNAL and never consult the PDP - independence from
        Local-Only state, not a policy exemption, is what "remains available"
        means (see network_policy.py's docstring for the measured reason:
        NETWORK_EXTERNAL is DENY-in-Local-Only even for a loopback target)."""
        import ast

        for name in ("ollama_adapter.py", "openai_compatible_adapter.py"):
            tree = ast.parse((PACKAGE_ROOT / name).read_text(encoding="utf-8"))
            imported = {
                n.module.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.module
            }
            assert "control" not in imported, name

    def test_a_real_loopback_call_succeeds_regardless_of_local_only_state(self) -> None:
        """The adapter itself, exercised directly: probing this real, running
        Ollama server never touches the PDP and never depends on Local-Only."""
        assert OllamaAdapter().probe().state is HonestState.PASS

    def test_local_only_denies_a_hypothetical_external_local_ai_target(self) -> None:
        """Never performs the call - classifies and asks the real PDP, the
        same 'attempt_fetch never calls out' boundary research.py established.
        This context's own adapters never construct such a target (Package 1's
        construction-time refusal); this proves the negative control would
        hold even if one were somehow attempted."""
        pdp = PolicyDecisionPoint.load(REPO)
        decision = gate_local_call(
            pdp, endpoint="http://203.0.113.9:11434", actor=ACTOR,
            trust_tier=TRUST_TIER, local_only=True,
        )
        assert decision == "DENY"

    def test_outside_local_only_the_external_target_is_ask_user_not_silent_auto(
        self,
    ) -> None:
        pdp = PolicyDecisionPoint.load(REPO)
        decision = gate_local_call(
            pdp, endpoint="http://203.0.113.9:11434", actor=ACTOR,
            trust_tier=TRUST_TIER, local_only=False,
        )
        assert decision == "ASK_USER"


class TestCondition0130DatasetVerificationDoesNotExist:
    """ARK-REQ-0130's own applicability rule requires ARK-REQ-0129 applicable
    AND dataset.verified_count > 0. The first half is true on this host
    (proved above); the second is honestly false: no dataset-verification
    authority exists anywhere in this repository, so no fine-tuning or
    distillation capability is built, attempted, or claimed."""

    def test_no_dataset_verification_authority_exists_anywhere(self) -> None:
        repo_arkali = REPO / "backend" / "arkali"
        offenders = [
            str(path.relative_to(REPO))
            for path in sorted(repo_arkali.rglob("*.py"))
            if "dataset" in path.read_text(encoding="utf-8").lower()
        ]
        assert not offenders, f"unexpected dataset-verification code: {offenders}"

    def test_engineering_localai_declares_no_fine_tuning_or_distillation_capability(
        self,
    ) -> None:
        offenders = [
            str(path.relative_to(REPO))
            for path in sorted(PACKAGE_ROOT.rglob("*.py"))
            for marker in ("fine_tun", "finetun", "distill")
            if marker in path.read_text(encoding="utf-8").lower()
        ]
        assert not offenders, f"unexpected fine-tuning/distillation code: {offenders}"
