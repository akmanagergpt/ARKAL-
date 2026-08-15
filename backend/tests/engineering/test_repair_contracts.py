from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from arkali.engineering.repair.contracts import (
    RepairBudget,
    RepairBudgetLedger,
    RepairFingerprint,
)
from arkali.engineering.repair.errors import (
    InvalidRepairFingerprintError,
    RepairBudgetExceededError,
    RepeatedFailedStrategyError,
)
from arkali.evidence.artifact.content_address import is_address


def fingerprint(**updates: object) -> RepairFingerprint:
    values: dict[str, object] = {
        "failure_signature": "pytest: test_contract",
        "root_cause_class": "contract-mismatch",
        "files": ("backend/z.py", "backend/a.py"),
        "strategy": "minimal-contract-repair",
        "provider_model": "local/qwen2.5-coder:14b",
        "outcome": "targeted-tests-pass",
    }
    values.update(updates)
    return RepairFingerprint.model_validate(values)


def ledger(**updates: object) -> RepairBudgetLedger:
    values: dict[str, object] = {
        "candidate_id": "candidate-14",
        "budget": RepairBudget(
            attempts=2,
            ai_calls=3,
            elapsed_seconds=120,
            cost=Decimal("1.50"),
            touched_files=4,
            regression_delta=1,
        ),
    }
    values.update(updates)
    return RepairBudgetLedger.model_validate(values)


class TestRepairFingerprint:
    def test_all_six_canonical_fields_are_required(self) -> None:
        fields = set(RepairFingerprint.model_fields)
        assert fields == {
            "failure_signature",
            "root_cause_class",
            "files",
            "strategy",
            "provider_model",
            "outcome",
        }
        for field in fields - {"files"}:
            with pytest.raises(ValidationError):
                fingerprint(**{field: ""})

        with pytest.raises(InvalidRepairFingerprintError):
            fingerprint(files=())

    def test_files_are_canonical_and_duplicates_are_refused(self) -> None:
        assert fingerprint().files == ("backend/a.py", "backend/z.py")
        with pytest.raises(InvalidRepairFingerprintError, match="only once"):
            fingerprint(files=("backend/a.py", "backend/a.py"))

    def test_fingerprint_is_immutable_deterministic_and_content_addressed(self) -> None:
        first = fingerprint()
        second = fingerprint(files=("backend/a.py", "backend/z.py"))
        assert first.rendering() == second.rendering()
        assert first.fingerprint == second.fingerprint
        assert is_address(first.fingerprint)
        with pytest.raises(ValidationError):
            first.outcome = "changed"  # type: ignore[misc]


class TestRepairBudgetLedger:
    def test_the_ledger_has_exactly_six_budget_dimensions(self) -> None:
        assert set(RepairBudget.model_fields) == {
            "attempts",
            "ai_calls",
            "elapsed_seconds",
            "cost",
            "touched_files",
            "regression_delta",
        }

    def test_record_returns_new_evidence_and_preserves_the_prior_ledger(self) -> None:
        original = ledger()
        recorded = original.record(
            fingerprint(), ai_calls=1, elapsed_seconds=30,
            cost=Decimal("0.25"), touched_files=2, regression_delta=0,
        )
        assert original.consumption.attempts == 0
        assert recorded.consumption.attempts == 1
        assert recorded.fingerprints == (fingerprint(),)
        assert is_address(recorded.ledger_ref)

    @pytest.mark.parametrize(
        ("field", "value"),
        (
            ("ai_calls", 4),
            ("elapsed_seconds", 121),
            ("cost", Decimal("1.51")),
            ("touched_files", 5),
            ("regression_delta", 2),
        ),
    )
    def test_each_measured_dimension_fails_closed(self, field: str, value: object) -> None:
        measurements: dict[str, object] = {
            "ai_calls": 0,
            "elapsed_seconds": 1,
            "cost": Decimal("0"),
            "touched_files": 1,
            "regression_delta": 0,
        }
        measurements[field] = value
        with pytest.raises(RepairBudgetExceededError, match=field):
            ledger().record(fingerprint(), **measurements)  # type: ignore[arg-type]

    def test_attempt_budget_is_enforced_by_recorded_fingerprints(self) -> None:
        first = ledger().record(
            fingerprint(strategy="strategy-a"), ai_calls=0, elapsed_seconds=1,
            cost=Decimal("0"), touched_files=1, regression_delta=0,
        )
        second = first.record(
            fingerprint(strategy="strategy-b"), ai_calls=0, elapsed_seconds=1,
            cost=Decimal("0"), touched_files=1, regression_delta=0,
        )
        with pytest.raises(RepairBudgetExceededError, match="attempts"):
            second.record(
                fingerprint(strategy="strategy-c"), ai_calls=0, elapsed_seconds=1,
                cost=Decimal("0"), touched_files=1, regression_delta=0,
            )


class TestAntiLoopRefusal:
    """C-26's declared verification responsibility: anti-loop property tests."""

    def test_repeats_failed_strategy_is_true_only_when_all_three_key_fields_match(
        self,
    ) -> None:
        base = fingerprint()
        recorded = ledger().record(
            base, ai_calls=0, elapsed_seconds=1,
            cost=Decimal("0"), touched_files=1, regression_delta=0,
        )
        variants = {
            "failure_signature": "pytest: a_different_test",
            "root_cause_class": "different-cause",
            "strategy": "a-different-strategy",
        }
        for field, other_value in variants.items():
            distinct = fingerprint(**{field: other_value})
            assert recorded.repeats_failed_strategy(distinct) is False
        assert recorded.repeats_failed_strategy(fingerprint()) is True

    @pytest.mark.parametrize(
        "irrelevant_field",
        ("files", "provider_model", "outcome"),
    )
    def test_files_provider_model_and_outcome_do_not_prevent_the_refusal(
        self, irrelevant_field: str,
    ) -> None:
        overrides: dict[str, object] = {
            "files": ("backend/other.py",),
            "provider_model": "local/a-different-model",
            "outcome": "a-different-outcome",
        }
        recorded = ledger().record(
            fingerprint(), ai_calls=0, elapsed_seconds=1,
            cost=Decimal("0"), touched_files=1, regression_delta=0,
        )
        repeat = fingerprint(**{irrelevant_field: overrides[irrelevant_field]})
        assert recorded.repeats_failed_strategy(repeat) is True
        with pytest.raises(RepeatedFailedStrategyError, match="minimal-contract-repair"):
            recorded.record(
                repeat, ai_calls=0, elapsed_seconds=1,
                cost=Decimal("0"), touched_files=1, regression_delta=0,
            )

    def test_record_refuses_a_repeated_strategy_before_touching_the_budget(self) -> None:
        recorded = ledger().record(
            fingerprint(), ai_calls=0, elapsed_seconds=1,
            cost=Decimal("0"), touched_files=1, regression_delta=0,
        )
        with pytest.raises(RepeatedFailedStrategyError) as excinfo:
            recorded.record(
                fingerprint(), ai_calls=0, elapsed_seconds=200,
                cost=Decimal("99"), touched_files=99, regression_delta=99,
            )
        assert "minimal-contract-repair" in str(excinfo.value)
        assert recorded.consumption.attempts == 1
        assert recorded.fingerprints == (fingerprint(),)

    def test_a_different_strategy_for_the_same_failure_is_permitted(self) -> None:
        recorded = ledger().record(
            fingerprint(), ai_calls=0, elapsed_seconds=1,
            cost=Decimal("0"), touched_files=1, regression_delta=0,
        )
        escalated_strategy = recorded.record(
            fingerprint(strategy="broader-contract-repair"), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"), touched_files=1,
            regression_delta=0,
        )
        assert escalated_strategy.consumption.attempts == 2
