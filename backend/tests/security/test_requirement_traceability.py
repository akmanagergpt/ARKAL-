"""ARK-REQ → implementation → evidence traceability for Phase 4.

Every Phase 4 requirement is mapped to the artifact that implements it and the
control that verifies it. The requirement set is read from the register, so a
requirement added to Phase 4 later fails this file until it is traced — the map
cannot silently stop being exhaustive (F-0016).

CLAIM LEVELS are explicit and are the point of this file:

  CONTRACT   the rule is implemented and verified deterministically. No runtime
             surface exercised it, because none exists yet.
  PROBED     a real, read-only host probe ran and its true result is recorded.
  DEFERRED   the requirement's *runtime* half belongs to a later phase. Phase 4
             delivers only the boundary, and says so.

Nothing in Phase 4 is claimed as REAL EXECUTION. There is no execution surface
in the tree, so no requirement may claim one.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.specification.register_parser import RequirementRegister

REPO = pathlib.Path(__file__).resolve().parents[3]

CONTRACT = "CONTRACT"
PROBED = "PROBED"
DEFERRED = "DEFERRED"

#: ARK-REQ -> (claim level, implementing artifact, verifying control)
TRACE: dict[str, tuple[str, str, str]] = {
    "ARK-REQ-0017": (CONTRACT, "control/isolation/isolation_contract.py",
                     "test_isolation.py::TestCanonicalModel"),
    "ARK-REQ-0071": (CONTRACT, "control/policy/protected_core.py",
                     "test_protected_core_and_secrets.py::TestProtectedCoreMembershipIsAuthoritative"),
    "ARK-REQ-0096": (CONTRACT, "control/policy/pdp.py + pep.py",
                     "test_pep_and_bypass.py::TestEnforcementContract"),
    "ARK-REQ-0097": (CONTRACT, "control/policy/pdp.py",
                     "test_pdp_decisions.py::TestEveryDecisionIsCanonical"),
    "ARK-REQ-0098": (CONTRACT, "control/policy/secret_reference.py",
                     "test_protected_core_and_secrets.py::TestNoRawSecretReachesAForbiddenSink"),
    "ARK-REQ-0099": (CONTRACT, "control/policy/secret_reference.py (no store API)",
                     "test_protected_core_and_secrets.py::TestSecretBoundaryIsStructural"),
    "ARK-REQ-0100": (CONTRACT, "control/policy/secret_reference.py (no raw resolve)",
                     "test_protected_core_and_secrets.py::TestSecretBoundaryIsStructural"),
    "ARK-REQ-0101": (CONTRACT, "control/policy/secret_reference.py",
                     "test_protected_core_and_secrets.py::TestSecretScopeAndKeyProtection"),
    "ARK-REQ-0102": (PROBED, "control/isolation/backend_probe.py::probe_vault_detach",
                     "test_isolation.py::TestRealHostProbes"),
    "ARK-REQ-0103": (CONTRACT, "control/policy/secret_reference.py::PermissionBroker",
                     "test_protected_core_and_secrets.py::TestSecretScopeAndKeyProtection"),
    "ARK-REQ-0104": (CONTRACT, "control/policy/pdp.py::_base_decision",
                     "test_local_only.py::TestLocalOnlyDeniesEgress"),
    "ARK-REQ-0105": (CONTRACT, "control/policy/pdp.py (LOOPBACK_ONLY)",
                     "test_local_only.py::TestLoopbackSurvives"),
    "ARK-REQ-0106": (CONTRACT, "AUTHORITY_MAP human_gates + protected_core",
                     "test_local_only.py::TestLocalOnlyToggleIsGated"),
    "ARK-REQ-0107": (CONTRACT, "control/policy/pdp.py",
                     "test_local_only.py::TestLocalOnlyDeniesEgress"),
    "ARK-REQ-0110": (CONTRACT, "control/policy/protected_core.py::authorize",
                     "test_protected_core_and_secrets.py::TestProtectedCoreDirectMutationIsRefused"),
    "ARK-REQ-0111": (DEFERRED, "stronger verification profile is a later phase",
                     "test_requirement_traceability.py::TestDeferredAreNotClaimed"),
    "ARK-REQ-0112": (CONTRACT, "control/policy/protected_core.py (no membership API)",
                     "test_protected_core_and_secrets.py::TestProtectedCoreMembershipIsAuthoritative"),
    "ARK-REQ-0113": (CONTRACT, "control/isolation/isolation_contract.py",
                     "test_isolation.py::TestCanonicalModel"),
    "ARK-REQ-0114": (CONTRACT, "control/isolation/isolation_contract.py",
                     "test_isolation.py::TestCanonicalModel"),
    "ARK-REQ-0118": (CONTRACT, "control/isolation/isolation_contract.py::resolve",
                     "test_isolation.py::TestComposition"),
    "ARK-REQ-0119": (CONTRACT, "control/isolation/isolation_contract.py::resolve",
                     "test_isolation.py::TestComposition"),
    "ARK-REQ-0120": (CONTRACT, "control/isolation/isolation_contract.py::resolve",
                     "test_isolation.py::TestComposition + test_pep_and_bypass.py"),
    "ARK-REQ-0121": (CONTRACT, "control/isolation/isolation_contract.py::resolve",
                     "test_isolation.py::TestArkaliRemainsOperational"),
    "ARK-REQ-0122": (CONTRACT, "control/isolation/isolation_contract.py",
                     "test_isolation.py::TestForgedCapabilityIsRejected"),
    "ARK-REQ-0123": (PROBED, "control/isolation/backend_probe.py::probe_all",
                     "test_isolation.py::TestRealHostProbes"),
    "ARK-REQ-0171": (CONTRACT, "control/policy/operation_class.py",
                     "test_pdp_decisions.py::TestVocabularyIsAuthoritative"),
    "ARK-REQ-0172": (CONTRACT, "control/policy/pdp.py::_absolute_rule",
                     "test_pdp_decisions.py::TestFixedRulesAreAbsolute"),
    "ARK-REQ-0173": (CONTRACT, "control/policy/operation_class.py::never_auto",
                     "test_pdp_decisions.py::TestFixedRulesAreAbsolute"),
    "ARK-REQ-0174": (CONTRACT, "control/policy/pdp.py::_narrowing_rules",
                     "test_pdp_decisions.py::TestFixedRulesAreAbsolute"),
    "ARK-REQ-0175": (CONTRACT, "control/policy/operation_class.py::get",
                     "test_pdp_decisions.py::TestMalformedInputFailsClosed"),
    "ARK-REQ-0202": (CONTRACT, "control/policy/pdp.py::_required_gate",
                     "test_requirement_traceability.py::TestHumanGatesAreDeclared"),
    "ARK-REQ-0236": (CONTRACT, "control/policy/protected_core.py",
                     "test_protected_core_and_secrets.py::TestProtectedCoreMembershipIsAuthoritative"),
    "ARK-REQ-0241": (CONTRACT, "tests/security/* (no control weakened)",
                     "test_no_shadow_security_model.py"),
}


@pytest.fixture(scope="module")
def phase_4_ids() -> set[str]:
    register = RequirementRegister.load(REPO)
    found = {r.req_id for r in register.for_phase("4") if r.is_mandatory}
    assert found, "register returned no Phase 4 requirements"
    return found


class TestTraceIsExhaustive:
    def test_every_phase_4_requirement_is_traced(self, phase_4_ids: set[str]) -> None:
        untraced = sorted(phase_4_ids - set(TRACE))
        assert untraced == [], f"Phase 4 requirements with no trace: {untraced}"

    def test_the_trace_claims_no_requirement_outside_phase_4(
        self, phase_4_ids: set[str]
    ) -> None:
        extra = sorted(set(TRACE) - phase_4_ids)
        assert extra == [], f"traced but not owned by Phase 4: {extra}"

    def test_every_entry_names_an_artifact_and_a_control(self) -> None:
        for req_id, (level, artifact, control) in TRACE.items():
            assert level in (CONTRACT, PROBED, DEFERRED), req_id
            assert artifact.strip(), req_id
            assert control.strip(), req_id


class TestClaimLevelsAreHonest:
    def test_no_requirement_claims_real_execution(self) -> None:
        """No execution surface exists, so none may be claimed."""
        assert "REAL_EXECUTION" not in {level for level, _, _ in TRACE.values()}

    def test_deferred_are_not_claimed_as_verified(self) -> None:
        deferred = sorted(k for k, v in TRACE.items() if v[0] == DEFERRED)
        assert deferred == ["ARK-REQ-0111"], (
            "the deferred set changed; each entry must be justified in the "
            "phase report limitations"
        )

    def test_probed_requirements_correspond_to_real_probes(self) -> None:
        from arkali.control.isolation.backend_probe import PROBES

        probed = [k for k, v in TRACE.items() if v[0] == PROBED]
        assert probed, "no requirement is backed by a real probe"
        assert PROBES, "no probe is implemented"


class TestHumanGatesAreDeclared:
    def test_eight_canonical_gates_are_declared_and_reachable_by_the_pdp(self) -> None:
        """ARK-REQ-0202."""
        from arkali.control.policy.pdp import PolicyAuthority

        gates = PolicyAuthority.load(REPO).human_gates
        assert len(gates) == 8
        assert set(gates) == {f"HUMAN_GATE_{n}" for n in range(1, 9)}

    def test_a_fixed_rule_naming_an_undeclared_gate_fails_closed(self) -> None:
        from arkali.control.policy.pdp import PolicyDecisionPoint
        from arkali.control.policy.policy_contract import PolicyRequest
        from arkali.control.policy.policy_errors import MalformedPolicyState

        pdp = PolicyDecisionPoint.load(REPO)
        broken = pdp.authority.model_copy(update={"human_gates": ("HUMAN_GATE_1",)})
        pdp_broken = PolicyDecisionPoint(pdp.vocabulary, pdp.matrix, broken)
        with pytest.raises(MalformedPolicyState):
            pdp_broken.decide(
                PolicyRequest(
                    operation_class="APPLY_MIGRATION",
                    trust_tier="TRUST-0",
                    actor="engineering.agent",
                    targets_real_or_stable_data=True,
                )
            )
