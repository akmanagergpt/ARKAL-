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
            fingerprint(), ai_calls=0, elapsed_seconds=1,
            cost=Decimal("0"), touched_files=1, regression_delta=0,
        )
        second = first.record(
            fingerprint(outcome="failed"), ai_calls=0, elapsed_seconds=1,
            cost=Decimal("0"), touched_files=1, regression_delta=0,
        )
        with pytest.raises(RepairBudgetExceededError, match="attempts"):
            second.record(
                fingerprint(outcome="escalated"), ai_calls=0, elapsed_seconds=1,
                cost=Decimal("0"), touched_files=1, regression_delta=0,
            )
