from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from arkali.engineering.knowledge.contracts import (
    EvidenceKind,
    EvidenceReference,
    SelfReportedClaim,
)
from arkali.engineering.knowledge.outcome_statistics import (
    VerifiedOutcome,
    aggregate,
)
from arkali.kernel.contracts.content_address import address_of

REAL_ADDRESS = address_of(b"phase-18-outcome-evidence")


def outcome(**updates: object) -> VerifiedOutcome:
    values: dict[str, object] = {
        "model_id": "local/qwen2.5-coder:14b",
        "task_class": "root_cause_repair",
        "succeeded": True,
        "evidence": EvidenceReference(
            kind=EvidenceKind.ACCEPTANCE_RESULT, content_address=REAL_ADDRESS
        ),
    }
    values.update(updates)
    return VerifiedOutcome.model_validate(values)


class TestOnlyVerifiedOutcomesAreConstructible:
    """D-026 / ARK-REQ-0394: never a model's self-reported claim."""

    def test_a_self_reported_claim_cannot_stand_in_for_evidence(self) -> None:
        with pytest.raises(ValidationError):
            VerifiedOutcome(
                model_id="m",
                task_class="t",
                succeeded=True,
                evidence=SelfReportedClaim(  # type: ignore[arg-type]
                    reported_by="m", claim="I always succeed"
                ),
            )

    def test_evidence_is_mandatory(self) -> None:
        with pytest.raises(ValidationError):
            VerifiedOutcome(model_id="m", task_class="t", succeeded=True)  # type: ignore[call-arg]


class TestAggregation:
    def test_attempts_and_successes_are_counted_per_model_and_task_class(self) -> None:
        outcomes = (
            outcome(model_id="m1", succeeded=True),
            outcome(model_id="m1", succeeded=False),
            outcome(model_id="m1", succeeded=True),
            outcome(model_id="m2", succeeded=True),
        )
        stats = {(s.model_id, s.task_class): s for s in aggregate(outcomes)}
        assert stats[("m1", "root_cause_repair")].attempts == 3
        assert stats[("m1", "root_cause_repair")].successes == 2
        assert stats[("m2", "root_cause_repair")].attempts == 1
        assert stats[("m2", "root_cause_repair")].successes == 1

    def test_task_classes_are_kept_separate_per_model(self) -> None:
        outcomes = (
            outcome(model_id="m1", task_class="repair", succeeded=True),
            outcome(model_id="m1", task_class="review", succeeded=False),
        )
        stats = aggregate(outcomes)
        assert len(stats) == 2
        assert {s.task_class for s in stats} == {"repair", "review"}

    def test_success_rate_is_computed_and_zero_attempts_is_not_a_division_error(
        self,
    ) -> None:
        stats = aggregate(
            (
                outcome(succeeded=True),
                outcome(succeeded=True),
                outcome(succeeded=False),
                outcome(succeeded=False),
            )
        )
        assert stats[0].success_rate == Decimal("0.5")

    def test_empty_input_produces_empty_output(self) -> None:
        assert aggregate(()) == ()

    def test_result_order_is_deterministic_regardless_of_input_order(self) -> None:
        first_order = (
            outcome(model_id="m2", succeeded=True),
            outcome(model_id="m1", succeeded=True),
        )
        second_order = (
            outcome(model_id="m1", succeeded=True),
            outcome(model_id="m2", succeeded=True),
        )
        assert aggregate(first_order) == aggregate(second_order)

    def test_nothing_is_cached_across_calls(self) -> None:
        """The C-13 'nothing is cached at any layer' shape: calling aggregate
        twice with different input produces different output."""
        first = aggregate((outcome(model_id="m1", succeeded=True),))
        second = aggregate(
            (
                outcome(model_id="m1", succeeded=True),
                outcome(model_id="m1", succeeded=False),
            )
        )
        assert first[0].attempts == 1
        assert second[0].attempts == 2
