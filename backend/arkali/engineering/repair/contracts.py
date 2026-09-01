"""C-26 immutable repair fingerprint, budget ledger and anti-loop refusal."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from arkali.engineering.repair.errors import (
    InvalidRepairFingerprintError,
    RepairBudgetExceededError,
    RepeatedFailedStrategyError,
)
from arkali.kernel.contracts.content_address import address_of

CONTRACT_VERSION: Final[str] = "1.0.0"


def content_hash(payload: bytes) -> str:
    """`engineering.repair`'s one real import of `kernel.contracts.content_
    address` -- every other real content hash this context needs (a golden
    repair corpus instance included) goes through this, rather than each
    caller adding its own separate import edge to an already fan-in-
    constrained kernel module (`architecture_budget_violation`,
    `max_fan_in_per_module`)."""
    return address_of(payload)


Declared = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]


class RepairFingerprint(BaseModel):
    """The exact six-field identity of one repair attempt and its outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    failure_signature: Declared
    root_cause_class: Declared
    files: tuple[Declared, ...]
    strategy: Declared
    provider_model: Declared
    outcome: Declared

    @field_validator("files")
    @classmethod
    def _canonical_files(cls, files: tuple[str, ...]) -> tuple[str, ...]:
        canonical = tuple(sorted(files))
        if not canonical:
            raise InvalidRepairFingerprintError("a repair must name at least one file")
        if len(set(canonical)) != len(canonical):
            raise InvalidRepairFingerprintError("a repair file may be named only once")
        return canonical

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def fingerprint(self) -> str:
        return address_of(self.rendering())


class RepairBudget(BaseModel):
    """Declared ceilings for every canonically required repair dimension."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempts: PositiveCount
    ai_calls: Count
    elapsed_seconds: PositiveCount
    cost: NonNegativeDecimal
    touched_files: PositiveCount
    regression_delta: Count


class RepairConsumption(BaseModel):
    """Cumulative evidence measured against a declared repair budget."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempts: Count = 0
    ai_calls: Count = 0
    elapsed_seconds: Count = 0
    cost: NonNegativeDecimal = Decimal("0")
    touched_files: Count = 0
    regression_delta: Count = 0


class RepairBudgetLedger(BaseModel):
    """Immutable, evidence-driven accounting for one candidate repair loop.

    ANTI-LOOP, BY STRUCTURE NOT BY READING `outcome`. `outcome` is declared
    free text (MS §Root-Cause names it as one of the six recorded fields, with
    no canonical vocabulary of pass/fail states for a single attempt — unlike
    the campaign-level `ESCALATED`/`BLOCKED` machines `STATE_MACHINES.md`
    defines elsewhere). A ledger is scoped to one candidate's convergence
    attempt on one defect, so a second fingerprint sharing its
    (`failure_signature`, `root_cause_class`, `strategy`) with one already in
    `fingerprints` is, by construction, a repeat of a strategy that did not
    resolve the defect the first time - otherwise there would be no reason to
    attempt it again in the same loop. `record` refuses that repeat directly,
    which is `ARK-REQ-0087`'s "repeated failed strategy escalates" enforced as
    a structural property rather than as text classification of `outcome`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str = CONTRACT_VERSION
    candidate_id: Declared
    budget: RepairBudget
    consumption: RepairConsumption = RepairConsumption()
    fingerprints: tuple[RepairFingerprint, ...] = ()

    @model_validator(mode="after")
    def _within_declared_budget(self) -> RepairBudgetLedger:
        if self.contract_version.split(".")[0] != CONTRACT_VERSION.split(".")[0]:
            raise RepairBudgetExceededError(
                f"contract major version {self.contract_version!r} is not readable"
            )
        exceeded = self.exceeded_dimensions()
        if exceeded:
            raise RepairBudgetExceededError(
                "repair budget exceeded: " + ", ".join(exceeded)
            )
        if len(self.fingerprints) != self.consumption.attempts:
            raise RepairBudgetExceededError(
                "attempt consumption must equal the recorded fingerprint count"
            )
        return self

    def exceeded_dimensions(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in RepairBudget.model_fields
            if getattr(self.consumption, name) > getattr(self.budget, name)
        )

    def repeats_failed_strategy(self, fingerprint: RepairFingerprint) -> bool:
        """Whether this ledger already recorded the same strategy for the same
        (failure, root cause) — the anti-loop identity `ARK-REQ-0087` and
        `ARK-REQ-0239` name. `files`, `provider_model` and `outcome` do not
        participate: a different file set or a different model attempting the
        identical strategy on the identical failure is still the same
        strategy repeating.
        """
        return any(
            existing.failure_signature == fingerprint.failure_signature
            and existing.root_cause_class == fingerprint.root_cause_class
            and existing.strategy == fingerprint.strategy
            for existing in self.fingerprints
        )

    def record(
        self,
        fingerprint: RepairFingerprint,
        *,
        ai_calls: int,
        elapsed_seconds: int,
        cost: Decimal,
        touched_files: int,
        regression_delta: int,
    ) -> RepairBudgetLedger:
        """Return a new ledger, or refuse the attempt before it can overrun or
        loop. Two refusals precede the budget math: an attempt whose
        (`failure_signature`, `root_cause_class`, `strategy`) repeats one
        already in `fingerprints` is `RepeatedFailedStrategyError`, never a
        budget dimension, because looping is a structural defect the caller
        must escalate rather than a ceiling it could raise.
        """
        if self.repeats_failed_strategy(fingerprint):
            raise RepeatedFailedStrategyError(
                "strategy "
                f"{fingerprint.strategy!r} already attempted for "
                f"failure {fingerprint.failure_signature!r} / "
                f"root cause {fingerprint.root_cause_class!r}; "
                "escalate instead of repeating it"
            )
        current = self.consumption
        updated = RepairConsumption(
            attempts=current.attempts + 1,
            ai_calls=current.ai_calls + ai_calls,
            elapsed_seconds=current.elapsed_seconds + elapsed_seconds,
            cost=current.cost + cost,
            touched_files=current.touched_files + touched_files,
            regression_delta=current.regression_delta + regression_delta,
        )
        return type(self).model_validate(
            {
                **self.model_dump(),
                "consumption": updated,
                "fingerprints": (*self.fingerprints, fingerprint),
            }
        )

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def ledger_ref(self) -> str:
        return address_of(self.rendering())
