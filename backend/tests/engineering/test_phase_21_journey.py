"""The composed Phase 21 real-authority journey (C-30).

Register denominator -> a real plugin manifest admitted through the real
PluginLifecycle state machine and the real 14-class operation vocabulary
(ARK-REQ-0164, 0165) -> an unmappable action resolved to a real, audited DENY
by the real PDP (ARK-REQ-0166) -> the TRUST-4 execution gate, isolation and a
per-execution human approval, neither substituting for the other, proven both
against a doubled ALLOW path and against this real, unconfigured host's
honest DENY (ARK-REQ-0117) -> Research's official-sources-first ordering and
its own real, PDP-governed network egress, including a real Local-Only DENY
(ARK-REQ-0163). ARK-REQ-0167 is OPTIONAL and not attempted here - the
register states plainly that optional entries never block release.

No AI provider is contacted anywhere in this journey.
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.isolation.backend_probe import probe_all
from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
)
from arkali.control.policy.operation_class import Decision, OperationClassVocabulary
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.plugin.errors import PluginExecutionRefusedError
from arkali.engineering.plugin.lifecycle_pipeline import APPROVED, admit_plugin
from arkali.engineering.plugin.manifest import PluginManifest
from arkali.engineering.plugin.research import (
    COMMUNITY,
    OFFICIAL,
    ResearchSource,
    attempt_fetch,
    resolve_sources,
)
from arkali.engineering.plugin.trust4_execution_gate import (
    TRUST_TIER,
    assert_execution_approved,
    execution_binding_ref,
)
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE_ROOT: Final[pathlib.Path] = REPO / "backend/arkali/engineering/plugin"

_MANDATORY_IDS: Final[frozenset[str]] = frozenset(
    {"ARK-REQ-0117", "ARK-REQ-0163", "ARK-REQ-0164", "ARK-REQ-0165", "ARK-REQ-0166"}
)
_OPTIONAL_IDS: Final[frozenset[str]] = frozenset({"ARK-REQ-0167"})


def test_step_0_no_ai_provider_is_contacted_anywhere_in_the_shipping_source() -> None:
    offenders = [
        f"{path.relative_to(REPO)}: {marker}"
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        for marker in ("openai", "anthropic", "requests.", "httpx.", "urllib.request")
        if marker in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"provider/transport marker present: {offenders}"


def test_step_1_the_real_register_denominator() -> None:
    register = RequirementRegister.load(REPO)
    phase21 = {r.req_id for r in register.for_phase("21")}
    assert phase21 == _MANDATORY_IDS | _OPTIONAL_IDS

    by_id = {r.req_id: r for r in register.for_phase("21")}
    for req_id in _MANDATORY_IDS:
        assert by_id[req_id].is_mandatory, req_id
    for req_id in _OPTIONAL_IDS:
        assert not by_id[req_id].is_mandatory, req_id

    owners = {r.req_id: r.owning_component for r in register.for_phase("21")}
    assert owners["ARK-REQ-0117"] == "control.policy"
    assert owners["ARK-REQ-0165"] == "control.policy"
    assert owners["ARK-REQ-0166"] == "control.policy"
    assert owners["ARK-REQ-0163"] == "engineering.plugin"
    assert owners["ARK-REQ-0164"] == "engineering.plugin"
    assert owners["ARK-REQ-0167"] == "engineering.plugin"


def test_step_2_state_machine_count_stays_twelve() -> None:
    """This phase adds no new machine - `PluginLifecycle` already existed
    (Phase 3) and is reused unmodified."""
    authority_map = AuthorityMap.load(REPO)
    assert len(authority_map.state_machine_authorities) == 12


@pytest.fixture(scope="module")
def vocabulary() -> OperationClassVocabulary:
    return OperationClassVocabulary.load(REPO)


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture(scope="module")
def isolation_authority() -> IsolationAuthority:
    return IsolationAuthority.load(REPO)


@pytest.fixture(scope="module")
def approval_gate() -> WorkflowApprovalGate:
    return WorkflowApprovalGate.load(REPO)


def _satisfied_backends(authority: IsolationAuthority) -> tuple[BackendDescriptor, ...]:
    declared = authority.declared_backends()
    return tuple(
        BackendDescriptor(name=name, provides=provides, availability=HonestState.PASS)
        for name, provides in declared.items()
    )


class TestCondition0164And0165ManifestAdmission:
    """ARK-REQ-0164 ("manifest/permission/version governed, cannot crash
    core") and ARK-REQ-0165 ("plugin permissions use the 14 canonical
    operation classes"), composed against the real, live vocabulary."""

    def test_a_manifest_with_every_permission_mappable_reaches_approved(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        manifest = PluginManifest(
            plugin_id="acme.journey-plugin", name="Journey Plugin", version="1.0.0",
            declared_permissions=vocabulary.names(),
        )
        outcome = admit_plugin(manifest, vocabulary)
        assert outcome.state == APPROVED
        assert outcome.manifest_ref == manifest.manifest_ref

    def test_a_governed_but_unmappable_permission_never_crashes_admission(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        """Cannot crash core: an unmappable declared permission is a named,
        recorded outcome, not an unhandled exception."""
        manifest = PluginManifest(
            plugin_id="acme.journey-plugin-2", name="Journey Plugin 2",
            version="1.0.0", declared_permissions=("READ_FILE", "HACK_THE_PLANET"),
        )
        outcome = admit_plugin(manifest, vocabulary)
        assert outcome.state != APPROVED
        assert outcome.unmappable_permissions == ("HACK_THE_PLANET",)

    def test_a_malformed_version_is_refused_at_construction_not_admission(self) -> None:
        """Version is governed (semver) - a malformed version is refused
        before a manifest can even reach the lifecycle."""
        from pydantic import ValidationError

        from arkali.engineering.plugin.errors import PluginManifestVersionError

        with pytest.raises((PluginManifestVersionError, ValidationError)):
            PluginManifest(
                plugin_id="acme.bad-version", name="Bad Version", version="not-semver",
            )


class TestCondition0166UnmappableActionIsDeny:
    def test_an_unmappable_action_resolves_to_a_real_recorded_deny(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        record = pdp.decide_or_deny_unmapped(
            PolicyRequest(
                operation_class="TELEPORT_USER", trust_tier="TRUST-0", actor="plugin",
            )
        )
        assert record.decision is Decision.DENY
        assert record.reason  # a real, audited decision, never a bare raise


class TestCondition0117Trust4ExecutionGate:
    """ARK-REQ-0117: TRUST-4 human approval PER execution - proven both
    against a doubled ALLOW path and against this real host's honest DENY."""

    def test_this_real_host_denies_trust_4_execution_honestly(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        backends = probe_all(isolation_authority, REPO)
        resolution = isolation_authority.resolve(TRUST_TIER, backends)
        if resolution.execution_decision == "ALLOW":
            pytest.skip("this host genuinely satisfies TRUST-4 isolation")
        ref = execution_binding_ref(
            plugin_id="acme.journey-plugin", manifest_ref="sha256:" + "a" * 64,
            action="run", execution_nonce="journey-attempt-1",
        )
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution, approval_gate=approval_gate,
                decision="APPROVED", actor="human_reviewer",
                approval_binding_hash=ref, execution_ref=ref,
            )

    def test_an_approval_never_carries_over_to_a_second_execution(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            TRUST_TIER, _satisfied_backends(isolation_authority)
        )
        first = execution_binding_ref(
            plugin_id="acme.journey-plugin", manifest_ref="sha256:" + "a" * 64,
            action="run", execution_nonce="journey-attempt-1",
        )
        second = execution_binding_ref(
            plugin_id="acme.journey-plugin", manifest_ref="sha256:" + "a" * 64,
            action="run", execution_nonce="journey-attempt-2",
        )
        assert_execution_approved(
            isolation_resolution=resolution, approval_gate=approval_gate,
            decision="APPROVED", actor="human_reviewer",
            approval_binding_hash=first, execution_ref=first,
        )  # attempt 1, genuinely approved for attempt 1
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution, approval_gate=approval_gate,
                decision="APPROVED", actor="human_reviewer",
                approval_binding_hash=first, execution_ref=second,
            )  # attempt 1's approval does not authorise attempt 2


class TestCondition0163ResearchOfficialSourcesAndNoMutation:
    def test_official_sources_are_tried_before_community_ones(self) -> None:
        official = ResearchSource(name="vendor", kind=OFFICIAL, url="https://vendor.example")
        community = ResearchSource(name="forum", kind=COMMUNITY, url="https://forum.example")
        resolved = resolve_sources((community, official))
        assert resolved == (official, community)

    def test_local_only_really_denies_researchs_own_network_egress(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        source = ResearchSource(name="vendor", kind=OFFICIAL, url="https://vendor.example")
        result = attempt_fetch(
            source, pdp, actor="engineering.plugin", trust_tier="TRUST-2",
            local_only=True,
        )
        assert result.decision == "DENY"
        assert result.mutation_applied is False
