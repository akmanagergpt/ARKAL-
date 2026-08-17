"""PDP determinism and the canonical decision model (ARK-REQ-0097, 0171-0175).

Every expectation is derived from the canonical matrix rather than transcribed,
so this file cannot drift from `SECURITY_ARCHITECTURE.md` §2. Where a specific
canonical sentence is asserted by name, the sentence is quoted in the test name.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.operation_class import Decision, OperationClassVocabulary
from arkali.control.policy.pdp import PolicyAuthority, PolicyDecisionPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.security_matrix import SecurityMatrix
from arkali.control.policy.policy_errors import (
    MalformedPolicyState,
    UnknownOperationClass,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture(scope="module")
def matrix() -> SecurityMatrix:
    return SecurityMatrix.load(REPO)


@pytest.fixture(scope="module")
def vocabulary() -> OperationClassVocabulary:
    return OperationClassVocabulary.load(REPO)


def request_for(operation: str, tier: str, **overrides: object) -> PolicyRequest:
    base: dict[str, object] = {
        "operation_class": operation,
        "trust_tier": tier,
        "actor": "engineering.agent",
    }
    base.update(overrides)
    return PolicyRequest(**base)  # type: ignore[arg-type]


class TestVocabularyIsAuthoritative:
    def test_fourteen_classes_are_declared(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        """ARK-REQ-0171. The count comes from the map, not from this test."""
        assert len(vocabulary) == 14
        assert len(vocabulary.names()) == len(set(vocabulary.names()))

    def test_matrix_and_map_declare_the_same_vocabulary(
        self, vocabulary: OperationClassVocabulary, matrix: SecurityMatrix
    ) -> None:
        """Two canonical sources; neither may drift from the other."""
        assert set(vocabulary.names()) == set(matrix.operation_classes())

    def test_every_class_resolves_at_every_tier(
        self, vocabulary: OperationClassVocabulary, matrix: SecurityMatrix
    ) -> None:
        tiers = matrix.tiers()
        assert len(tiers) == 5, f"expected five trust tiers, parsed {tiers}"
        for name in vocabulary.names():
            for tier in tiers:
                assert matrix.resolution(name, tier).decision in set(Decision)

    def test_unmapped_resolution_is_deny(
        self, vocabulary: OperationClassVocabulary
    ) -> None:
        assert vocabulary.unmapped_resolution is Decision.DENY


class TestEveryDecisionIsCanonical:
    def test_pdp_never_contradicts_the_matrix_without_a_narrowing_reason(
        self, pdp: PolicyDecisionPoint, matrix: SecurityMatrix
    ) -> None:
        """A decision may be stricter than the matrix, never more permissive."""
        order = {Decision.AUTO: 0, Decision.ASK_USER: 1, Decision.DENY: 2}
        checked = 0
        for name in matrix.operation_classes():
            for tier in matrix.tiers():
                expected = matrix.resolution(name, tier).decision
                actual = pdp.decide(
                    request_for(
                        name,
                        tier,
                        target_is_loopback=True,
                        target_is_own_process=True,
                        within_preauthorized_scope=True,
                        lockfile_bound=True,
                        actor="lifecycle.recovery",
                    )
                ).decision
                assert order[actual] >= order[expected], (
                    f"{name}@{tier}: PDP {actual} is more permissive than "
                    f"canonical {expected}"
                )
                checked += 1
        assert checked == 70, f"expected 14x5 resolutions, checked {checked}"


class TestFixedRulesAreAbsolute:
    @pytest.mark.parametrize("tier", ["TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"])
    def test_write_stable_file_is_deny_for_every_actor(
        self, pdp: PolicyDecisionPoint, tier: str
    ) -> None:
        """ARK-REQ-0172: DENY for every actor, always."""
        for actor in ("engineering.agent", "lifecycle.release", "lifecycle.recovery",
                      "human_operator", "acceptance.engine"):
            record = pdp.decide(request_for("WRITE_STABLE_FILE", tier, actor=actor))
            assert record.decision is Decision.DENY

    def test_write_stable_file_cannot_be_widened_by_any_fact(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        record = pdp.decide(
            request_for(
                "WRITE_STABLE_FILE",
                "TRUST-0",
                actor="lifecycle.recovery",
                within_preauthorized_scope=True,
                lockfile_bound=True,
                target_is_loopback=True,
                recorded_human_gates=("HUMAN_GATE_2", "HUMAN_GATE_4"),
            )
        )
        assert record.decision is Decision.DENY

    def test_rollback_stable_is_denied_to_ordinary_actors(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """Recovery Supervisor only. The Supervisor itself is a later phase."""
        for actor in ("engineering.agent", "lifecycle.release", "workflow",
                      "engineering.plugin", "surfaces.operations"):
            record = pdp.decide(request_for("ROLLBACK_STABLE", "TRUST-0", actor=actor))
            assert record.decision is Decision.DENY

    def test_rollback_is_denied_even_to_the_canonical_invoker_at_this_phase(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """The one carve-out needs a verified Recovery Supervisor (Phase 22B).

        Granting anything now would grant it to a component that does not exist
        and whose canonical preconditions cannot be checked.
        """
        invoker = PolicyAuthority.load(REPO).rollback_invoker
        record = pdp.decide(request_for("ROLLBACK_STABLE", "TRUST-0", actor=invoker))
        assert record.decision is Decision.DENY
        assert invoker in record.reason, "the reason must name the canonical invoker"

    def test_rollback_invoker_is_read_from_authority_not_hard_coded(self) -> None:
        assert PolicyAuthority.load(REPO).rollback_invoker == "lifecycle.recovery"

    def test_stable_direct_mutation_is_permitted_to_nobody(self) -> None:
        """`direct_mutation_permitted_by: []` - empty by design."""
        assert PolicyAuthority.load(REPO).stable_direct_mutation_permitted_by == ()

    @pytest.mark.parametrize(
        "operation", ["INSTALL_SYSTEM_SOFTWARE", "CHANGE_SYSTEM_CONFIGURATION"]
    )
    @pytest.mark.parametrize("tier", ["TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"])
    def test_never_auto_classes_are_never_auto(
        self, pdp: PolicyDecisionPoint, operation: str, tier: str
    ) -> None:
        """ARK-REQ-0173."""
        record = pdp.decide(request_for(operation, tier))
        assert record.decision is not Decision.AUTO

    def test_access_secret_is_never_auto_outside_scope(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """ARK-REQ-0174."""
        for tier in ("TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"):
            outside = pdp.decide(
                request_for("ACCESS_SECRET", tier, within_preauthorized_scope=False)
            )
            assert outside.decision is Decision.DENY
            unstated = pdp.decide(request_for("ACCESS_SECRET", tier))
            assert unstated.decision is Decision.DENY

    def test_access_secret_may_be_auto_only_inside_scope_at_low_tiers(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        record = pdp.decide(
            request_for("ACCESS_SECRET", "TRUST-0", within_preauthorized_scope=True)
        )
        assert record.decision is Decision.AUTO
        high = pdp.decide(
            request_for("ACCESS_SECRET", "TRUST-2", within_preauthorized_scope=True)
        )
        assert high.decision is Decision.DENY

    def test_terminate_process_is_refused_across_a_boundary(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        assert pdp.decide(
            request_for("TERMINATE_PROCESS", "TRUST-0", target_is_own_process=False)
        ).decision is Decision.DENY
        assert pdp.decide(
            request_for("TERMINATE_PROCESS", "TRUST-0", target_is_own_process=True)
        ).decision is Decision.AUTO

    def test_browser_local_is_refused_off_loopback(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        assert pdp.decide(
            request_for("BROWSER_LOCAL", "TRUST-0", target_is_loopback=False)
        ).decision is Decision.DENY
        assert pdp.decide(
            request_for("BROWSER_LOCAL", "TRUST-0", target_is_loopback=True)
        ).decision is Decision.AUTO

    def test_apply_migration_on_real_data_requires_gate_6(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        record = pdp.decide(
            request_for(
                "APPLY_MIGRATION", "TRUST-0", targets_real_or_stable_data=True
            )
        )
        assert record.required_human_gate == "HUMAN_GATE_6"
        assert record.decision is not Decision.AUTO


class TestUnstatedFactsFailClosed:
    @pytest.mark.parametrize(
        "operation", ["BROWSER_LOCAL", "TERMINATE_PROCESS", "ACCESS_SECRET"]
    )
    def test_an_unstated_required_fact_is_not_assumed_permissive(
        self, pdp: PolicyDecisionPoint, operation: str
    ) -> None:
        """`None` means 'not stated' and must never resolve to the permissive value."""
        record = pdp.decide(request_for(operation, "TRUST-0"))
        assert record.decision is Decision.DENY


class TestDeterminism:
    def test_same_facts_give_identical_records(
        self, pdp: PolicyDecisionPoint, matrix: SecurityMatrix
    ) -> None:
        for name in matrix.operation_classes():
            request = request_for(name, "TRUST-2")
            rendered = {pdp.decide(request).model_dump_json() for _ in range(5)}
            assert len(rendered) == 1

    def test_a_second_pdp_instance_agrees(self, matrix: SecurityMatrix) -> None:
        """There is one decision model, not one per instance."""
        first, second = PolicyDecisionPoint.load(REPO), PolicyDecisionPoint.load(REPO)
        for name in matrix.operation_classes():
            for tier in matrix.tiers():
                request = request_for(name, tier)
                assert first.decide(request).decision == second.decide(request).decision


class TestMalformedInputFailsClosed:
    def test_unknown_operation_class_is_refused(self, pdp: PolicyDecisionPoint) -> None:
        with pytest.raises(UnknownOperationClass):
            pdp.decide(request_for("INVENT_AN_OPERATION", "TRUST-0"))

    @pytest.mark.parametrize("tier", ["TRUST-9", "trust-0", "", "TIER-1", "TRUST"])
    def test_unknown_trust_tier_is_refused(
        self, pdp: PolicyDecisionPoint, tier: str
    ) -> None:
        with pytest.raises(MalformedPolicyState):
            pdp.decide(request_for("READ_FILE", tier))

    def test_no_decision_path_returns_none(
        self, pdp: PolicyDecisionPoint, matrix: SecurityMatrix
    ) -> None:
        """Every reachable combination produces a real decision, never None."""
        for name in matrix.operation_classes():
            for tier in matrix.tiers():
                record = pdp.decide(request_for(name, tier))
                assert record.decision in set(Decision)
                assert record.reason


class TestDecideOrDenyUnmappedNeverRaisesForAnUnmappableClass:
    """ARK-REQ-0166: "Unmappable plugin action is DENY." `decide` itself is
    unchanged (`TestMalformedInputFailsClosed` above still proves it raises);
    this is the additive, total entry point a caller that cannot afford an
    uncaught exception (a plugin action invocation) uses instead."""

    def test_an_unmappable_class_resolves_rather_than_raises(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        record = pdp.decide_or_deny_unmapped(
            request_for("INVENT_AN_OPERATION", "TRUST-0")
        )
        assert record.decision is Decision.DENY

    def test_the_resolution_is_read_from_the_authority_map_not_hard_coded(
        self, pdp: PolicyDecisionPoint, vocabulary: OperationClassVocabulary
    ) -> None:
        record = pdp.decide_or_deny_unmapped(
            request_for("INVENT_AN_OPERATION", "TRUST-0")
        )
        assert record.decision is vocabulary.unmapped_resolution

    def test_the_decision_is_a_real_audited_record_not_an_exception(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        record = pdp.decide_or_deny_unmapped(
            request_for("NOT_A_REAL_CLASS", "TRUST-2")
        )
        assert record.operation_class == "NOT_A_REAL_CLASS"
        assert record.trust_tier == "TRUST-2"
        assert record.reason
        assert "unmapped_action_resolution" in record.reason

    def test_a_mappable_class_still_resolves_exactly_as_decide_would(
        self, pdp: PolicyDecisionPoint, matrix: SecurityMatrix
    ) -> None:
        """The total variant must not silently diverge from `decide` for the
        classes that DO map — only the unmappable path is new behaviour."""
        for name in matrix.operation_classes():
            for tier in matrix.tiers():
                request = request_for(name, tier)
                assert (
                    pdp.decide_or_deny_unmapped(request).decision
                    == pdp.decide(request).decision
                )

    def test_an_unknown_trust_tier_still_raises_even_when_unmapped(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """The new leniency is scoped to the operation-class check only —
        a genuinely malformed tier must still fail closed by raising."""
        with pytest.raises(MalformedPolicyState):
            pdp.decide_or_deny_unmapped(request_for("INVENT_AN_OPERATION", "NOT-A-TIER"))

    def test_decide_itself_is_unmodified_and_still_raises(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """This is the entry point most existing callers already use; it
        must not have been quietly weakened by this addition."""
        with pytest.raises(UnknownOperationClass):
            pdp.decide(request_for("INVENT_AN_OPERATION", "TRUST-0"))
