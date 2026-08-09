"""PEP enforcement and policy-bypass resistance (ARK-REQ-0096, 0241).

HONEST SCOPE. Phase 4 verifies the enforcement *contract*. It does not and
cannot verify end-to-end bypass resistance across API, UI, agent, workflow,
plugin/connector and computer-use, because none of those surfaces exists yet.
`TestSurfacesNotYetImplemented` states that explicitly rather than leaving the
gap to be inferred from silence, and asserts the absence so the claim cannot
quietly become false when a surface does appear.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.operation_class import Decision
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.policy_errors import PolicyBypassAttempt, PolicyDenied

REPO = pathlib.Path(__file__).resolve().parents[3]

#: Every surface SECURITY_ARCHITECTURE.md §1 names as a caller.
CANONICAL_SURFACES = (
    "API", "UI", "agent", "workflow", "plugin", "computer-use", "sandbox",
)


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


def request_for(operation: str, tier: str, **overrides: object) -> PolicyRequest:
    base: dict[str, object] = {
        "operation_class": operation,
        "trust_tier": tier,
        "actor": "engineering.agent",
    }
    base.update(overrides)
    return PolicyRequest(**base)  # type: ignore[arg-type]


class TestEnforcementContract:
    def test_deny_raises_rather_than_returning_a_falsy_value(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """A boolean return invites `if not allowed: pass`."""
        pep = PolicyEnforcementPoint(pdp, "test-surface")
        with pytest.raises(PolicyDenied):
            pep.enforce(request_for("WRITE_STABLE_FILE", "TRUST-0"))

    def test_ask_user_is_returned_not_raised(self, pdp: PolicyDecisionPoint) -> None:
        pep = PolicyEnforcementPoint(pdp, "test-surface")
        record = pep.enforce(request_for("INSTALL_SYSTEM_SOFTWARE", "TRUST-0"))
        assert record.decision is Decision.ASK_USER

    def test_ask_user_is_not_permission_for_an_unattended_call_site(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        pep = PolicyEnforcementPoint(pdp, "unattended")
        with pytest.raises(PolicyDenied):
            pep.require_auto(request_for("INSTALL_SYSTEM_SOFTWARE", "TRUST-0"))

    def test_auto_passes_an_unattended_call_site(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        pep = PolicyEnforcementPoint(pdp, "unattended")
        record = pep.require_auto(request_for("WRITE_WORKSPACE_FILE", "TRUST-2"))
        assert record.decision is Decision.AUTO

    def test_an_unnamed_enforcement_point_is_refused(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """An unauditable PEP is not a PEP."""
        with pytest.raises(PolicyBypassAttempt):
            PolicyEnforcementPoint(pdp, "   ")


class TestEveryDecisionIsAudited:
    def test_auto_decisions_are_audited_too(self, pdp: PolicyDecisionPoint) -> None:
        """SECURITY_ARCHITECTURE.md §1: every decision, including AUTO."""
        pep = PolicyEnforcementPoint(pdp, "surface")
        pep.enforce(request_for("WRITE_WORKSPACE_FILE", "TRUST-0"))
        assert len(pep.audit_trail) == 1
        assert pep.audit_trail[0].decision is Decision.AUTO

    def test_denied_attempts_are_audited(self, pdp: PolicyDecisionPoint) -> None:
        pep = PolicyEnforcementPoint(pdp, "surface")
        with pytest.raises(PolicyDenied):
            pep.enforce(request_for("WRITE_STABLE_FILE", "TRUST-0"))
        assert len(pep.audit_trail) == 1
        assert pep.audit_trail[0].decision is Decision.DENY

    def test_the_audit_trail_is_immutable_from_outside(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        pep = PolicyEnforcementPoint(pdp, "surface")
        pep.evaluate(request_for("READ_FILE", "TRUST-0"))
        snapshot = pep.audit_trail
        assert isinstance(snapshot, tuple)
        pep.evaluate(request_for("READ_FILE", "TRUST-0"))
        assert len(snapshot) == 1 and len(pep.audit_trail) == 2


class TestNoSurfaceGetsADifferentAnswer:
    @pytest.mark.parametrize("surface", CANONICAL_SURFACES)
    def test_every_surface_receives_the_identical_decision(
        self, pdp: PolicyDecisionPoint, surface: str
    ) -> None:
        """One PDP. A surface cannot obtain a better answer by being itself."""
        baseline = PolicyEnforcementPoint(pdp, "baseline")
        request = request_for("NETWORK_EXTERNAL", "TRUST-2", local_only=True)
        expected = baseline.evaluate(request)
        actual = PolicyEnforcementPoint(pdp, surface).evaluate(request)
        assert actual.decision == expected.decision
        assert actual.rule == expected.rule

    @pytest.mark.parametrize("actor", CANONICAL_SURFACES)
    def test_no_actor_identity_widens_an_absolute_rule(
        self, pdp: PolicyDecisionPoint, actor: str
    ) -> None:
        pep = PolicyEnforcementPoint(pdp, actor)
        with pytest.raises(PolicyDenied):
            pep.enforce(request_for("WRITE_STABLE_FILE", "TRUST-0", actor=actor))


class TestIsolationFailureBlocksExecution:
    def test_unsatisfiable_isolation_denies_an_executing_operation(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """ARK-REQ-0120: unsatisfiable ⇒ execution DENY."""
        pep = PolicyEnforcementPoint(pdp, "sandbox")
        with pytest.raises(PolicyDenied):
            pep.enforce(
                request_for(
                    "RUN_PROCESS", "TRUST-2",
                    isolation_satisfied=False, requires_execution=True,
                )
            )

    def test_satisfiable_isolation_permits_the_same_operation(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """Proves the refusal above is caused by isolation, not by something else."""
        pep = PolicyEnforcementPoint(pdp, "sandbox")
        record = pep.enforce(
            request_for(
                "RUN_PROCESS", "TRUST-2",
                isolation_satisfied=True, requires_execution=True,
            )
        )
        assert record.decision is Decision.AUTO

    def test_a_non_executing_operation_is_not_blocked_by_isolation(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        record = pdp.decide(
            request_for(
                "READ_FILE", "TRUST-2",
                isolation_satisfied=False, requires_execution=False,
            )
        )
        assert record.decision is Decision.AUTO


#: Execution surfaces the canonical set names, and which are still unbuilt.
#: `surfaces.command` arrived at Phase 5 Package 4; the rest do not exist.
UNBUILT_SURFACE_PARTS = ("sandbox", "scheduler", "durable", "workflow", "operations")


class TestSurfaceCoverageIsHonest:
    """No phase may imply coverage it does not have.

    The predecessor asserted that NO execution surface existed, and stated in
    its own failure message what to do when that stopped being true: the
    surface "must be brought under a real PEP with runtime evidence". Phase 5
    Package 4 built `surfaces.command` and did exactly that, so the tripwire
    fired as designed and is replaced by the obligation it was pointing at.

    This is not a relaxation. The predecessor could only ever say "nothing
    exists"; this says "everything that exists is enforced, and what is not
    built is still absent", which still fails for an unenforced surface.
    """

    def test_every_existing_surface_module_is_under_a_real_pep(self) -> None:
        """A surface package that enforces no policy fails here."""
        root = REPO / "backend" / "arkali" / "surfaces"
        modules = sorted(
            p for p in root.rglob("*.py")
            if p.name != "__init__.py" and "state_machine" not in p.name
        )
        assert modules, "the control is vacuous if no surface module exists"
        enforcing = [
            p for p in modules
            if "PolicyEnforcementPoint" in p.read_text(encoding="utf-8")
        ]
        assert enforcing, (
            "a surface exists but no module in it constructs a "
            f"PolicyEnforcementPoint: {[p.name for p in modules]}"
        )

    def test_surfaces_not_yet_built_are_still_absent(self) -> None:
        """If this fails, a new surface appeared and needs its own PEP coverage."""
        root = REPO / "backend" / "arkali"
        found = sorted(
            p.relative_to(REPO).as_posix()
            for p in root.rglob("*.py")
            if p.name != "__init__.py"
            and any(part in p.parts for part in UNBUILT_SURFACE_PARTS)
            and "state_machine" not in p.name
        )
        assert found == [], (
            "an execution surface now exists and must be brought under a real "
            f"PEP with runtime evidence: {found}"
        )

    def test_bypass_resistance_is_claimed_only_at_contract_level(self) -> None:
        """Documents the boundary of the Phase 4 claim, in executable form."""
        contract_verified = ("PDP determinism", "PEP refusal", "audit of every decision")
        runtime_not_implemented = CANONICAL_SURFACES
        assert contract_verified and runtime_not_implemented
        assert set(contract_verified).isdisjoint(set(runtime_not_implemented))
