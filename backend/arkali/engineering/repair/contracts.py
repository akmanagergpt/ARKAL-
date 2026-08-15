"""C-26 immutable repair fingerprint and six-dimensional budget ledger."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from arkali.engineering.repair.errors import (
    InvalidRepairFingerprintError,
    RepairBudgetExceededError,
)
from arkali.kernel.contracts.content_address import address_of

CONTRACT_VERSION: Final[str] = "1.0.0"
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
    """Immutable, evidence-driven accounting for one candidate repair loop."""

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
        """Return a new ledger or refuse the attempt before it can overrun."""
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
