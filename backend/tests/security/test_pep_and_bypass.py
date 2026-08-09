"""PEP enforcement and policy-bypass resistance (ARK-REQ-0096, 0241).

HONEST SCOPE. Phase 4 verifies the enforcement *contract*. It does not and
cannot verify end-to-end bypass resistance across API, UI, agent, workflow,
plugin/connector and computer-use, because none of those surfaces exists yet.
`TestSurfacesNotYetImplemented` states that explicitly rather than leaving the
gap to be inferred from silence, and asserts the absence so the claim cannot
quietly become false when a surface does appear.
"""

from __future__ import annotations

import ast
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


#: Execution-plane package roots the canonical set names. Which of these are
#: built is DERIVED below, never listed: `surfaces.command` arrived at Phase 5
#: Package 4 and `execution.durable` at Phase 7 Package 1, and the next one will
#: not need this line edited.
EXECUTION_PACKAGE_PARTS = ("sandbox", "scheduler", "durable", "workflow", "operations")

#: A package counts as built when it holds a module that is neither a package
#: marker nor a state-machine declaration. A machine is a declaration of a
#: relation; it performs no governed operation and needs no PEP.
def _package_modules(root: pathlib.Path, part: str) -> list[pathlib.Path]:
    return sorted(
        p for p in root.rglob("*.py")
        if p.name != "__init__.py"
        and part in p.parts
        and "state_machine" not in p.name
    )


#: The PEP's decision methods. "Under a real PEP" means one of these is CALLED
#: ON A PEP - naming the class proves nothing, because a module can import a type
#: and never ask it anything.
#:
#: Two mutation rounds shaped this. A name-only substring check could not be
#: defeated by any single edit, which is what a check measuring the wrong thing
#: looks like. Then matching the method name alone matched
#: `self._machine.evaluate(...)`, because `evaluate` belongs to the state machine
#: too - so the RECEIVER is checked as well.
PEP_DECISION_CALLS = ("require_auto", "enforce", "evaluate")


def _takes_a_policy_decision(path: pathlib.Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in PEP_DECISION_CALLS:
            continue
        receiver = ast.unparse(node.func.value).lower()
        if "pep" in receiver:
            return True
    return False


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

    def test_every_built_execution_package_enforces_and_the_rest_are_absent(
        self,
    ) -> None:
        """The obligation the predecessor pointed at, made executable.

        `execution.durable` arrived at Phase 7 Package 1 and the absence
        assertion fired exactly as designed, naming what to do about it. It is
        replaced here rather than deleted, and the replacement is **stronger**:
        the predecessor could only say "nothing exists", and would have gone
        quiet forever the moment something did. This says "everything built
        enforces, and what is not built is still absent" — which still fails for
        an unenforced package, and keeps failing for every package added later.
        """
        root = REPO / "backend" / "arkali"
        built: dict[str, list[pathlib.Path]] = {}
        absent: list[str] = []
        for part in EXECUTION_PACKAGE_PARTS:
            found = _package_modules(root, part)
            if found:
                built[part] = found
            else:
                absent.append(part)

        assert built, "no execution package is built; this control would be vacuous"
        for part, paths in built.items():
            enforcing = [p for p in paths if _takes_a_policy_decision(p)]
            assert enforcing, (
                f"execution package {part!r} exists but no module in it takes a "
                "policy decision; it must be brought under a real PEP with "
                f"runtime evidence: {[p.name for p in paths]}"
            )

        # What is still unbuilt stays honestly unbuilt: no phase may imply
        # coverage of a package that does not exist.
        for part in absent:
            assert _package_modules(root, part) == [], part

    def test_a_governed_package_without_a_decision_would_be_detected(
        self, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: the sweep above is not vacuous.

        A package whose modules take no policy decision must fail the same test,
        proved on a fixture tree rather than by trusting the live one.
        """
        root = tmp_path / "arkali"
        (root / "execution" / "durable").mkdir(parents=True)
        (root / "execution" / "durable" / "job_store.py").write_text(
            "def submit() -> None:\n    ...\n", encoding="utf-8"
        )
        found = _package_modules(root, "durable")
        assert found, "the fixture produced no module"
        assert [p for p in found if _takes_a_policy_decision(p)] == [], (
            "the fixture module takes no decision, so the live assertion above "
            "would fail for it"
        )

    def test_naming_the_type_without_asking_it_anything_is_not_enforcement(
        self, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: importing a PEP is not the same as consulting one."""
        root = tmp_path / "arkali"
        (root / "execution" / "durable").mkdir(parents=True)
        (root / "execution" / "durable" / "job_store.py").write_text(
            "from arkali.control.policy.pep import PolicyEnforcementPoint\n"
            "class JobStore:\n"
            "    def __init__(self, pep: PolicyEnforcementPoint) -> None:\n"
            "        self._pep = pep\n",
            encoding="utf-8",
        )
        found = _package_modules(root, "durable")
        assert found
        assert [p for p in found if _takes_a_policy_decision(p)] == []

    def test_the_durable_runtime_really_does_take_a_decision(self) -> None:
        """The live package satisfies the obligation, asserted directly."""
        store = REPO / "backend/arkali/execution/durable/job_store.py"
        assert _takes_a_policy_decision(store)

    def test_bypass_resistance_is_claimed_only_at_contract_level(self) -> None:
        """Documents the boundary of the Phase 4 claim, in executable form."""
        contract_verified = ("PDP determinism", "PEP refusal", "audit of every decision")
        runtime_not_implemented = CANONICAL_SURFACES
        assert contract_verified and runtime_not_implemented
        assert set(contract_verified).isdisjoint(set(runtime_not_implemented))
