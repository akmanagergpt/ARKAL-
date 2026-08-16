"""ARK-REQ-0086 / ARK-REQ-0238: the executable Phase 14 root-cause pipeline.

Owner: engineering.repair.

D-024 (docs/build/DECISION_LOG.md) is a human governance ruling: BP §Failure
protocol's 11-stage sequence is the single executable, machine-enforced
Phase 14 pipeline; MS §Root-Cause's 9-stage sequence remains the higher-level
conceptual description and is never implemented as a competing state
machine. `FailureProtocolVocabulary.bp_stages()` (Phase 14 Package 3) already
derives that 11-stage sequence from `BP §Failure protocol` at call time — the
stage list is never written a second time here.

NOT A THIRTEENTH STATE MACHINE. `STATE_MACHINES.md` declares exactly 12, none
of them a repair/failure-protocol machine, and every prior C-2x contract that
needed no new one says so explicitly. `RepairPipelinePath` is a RECEIPTED
PATH, the same shape `lifecycle.release.stable_path.StableCandidatePath`
already uses for `stable_mutation.required_path`: an ordered sequence with a
receipt proving the complete traversed prefix, refusing a skip, reorder,
repeat or unknown stage — not a state machine with arbitrary transition
rules. `lifecycle` is layer rank 5 and `engineering` is rank 4, so this
context may not import that one upward; the shape is mirrored, not reused,
because reuse across that edge is architecturally impossible.

EVIDENCE-DRIVEN, NEVER A FABRICATED STATUS STRING. `resolve_attempt` derives
the terminal `Accept/Reject` outcome from `AttemptEvidence`'s two measured
facts — never from a bare "accepted" flag — and records it through the
existing `RepairBudgetLedger`,
which already enforces the six budget dimensions and the anti-loop refusal
(Packages 1-2). A repeated failed strategy or an exceeded budget dimension
raises there, before any outcome could be recorded, which is this pipeline's
honest terminal state for a loop that must escalate rather than continue.

NO CANDIDATE, EVIDENCE, ACCEPTANCE, POLICY OR RELEASE AUTHORITY IS CREATED
HERE. This module performs no I/O and executes no transformer: `Candidate`
is a stage name in the receipted path, not a call into
`engineering.candidate`'s workspace (a same-layer context this one may not
import). Confinement to that stage is `ARK-REQ-0240`'s (Package 4), asked of
`control.policy`, never re-decided here.
"""

from __future__ import annotations

import pathlib
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.engineering.repair.contracts import RepairBudgetLedger, RepairFingerprint
from arkali.engineering.repair.errors import IllegalPipelineTransition
from arkali.engineering.repair.failure_protocol import FailureProtocolVocabulary

#: The two terminal outcomes `Accept/Reject` (the governed stage name) can
#: derive. Not invented: BP §Failure protocol names this stage itself, and no
#: canonical vocabulary exists for a single attempt's outcome beyond it
#: (Package 2) — the campaign-level `ESCALATED`/`BLOCKED` machines are
#: Phase 30/35's, not this stage's.
RESOLVED: Final[str] = "resolved"
REJECTED: Final[str] = "rejected"


class RepairStageReceipt(BaseModel):
    """Immutable proof that one repair attempt reached one governed stage."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    attempt_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    traversed: tuple[str, ...]


class RepairPipelinePath:
    """Advance a repair attempt only one BP-declared stage at a time."""

    def __init__(self, stages: tuple[str, ...], source: str) -> None:
        if len(stages) < 2 or len(set(stages)) != len(stages):
            raise IllegalPipelineTransition(
                "the failure-protocol path must be non-vacuous and unique"
            )
        self._stages = stages
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> RepairPipelinePath:
        vocabulary = FailureProtocolVocabulary.load(repo_root)
        stages = tuple(stage.strip().lower() for stage in vocabulary.bp_stages())
        return cls(stages, " + ".join(vocabulary.sources))

    def stages(self) -> tuple[str, ...]:
        return self._stages

    def begin(self, *, attempt_id: str) -> RepairStageReceipt:
        """Every attempt starts at the governed first stage, `Reproduce`."""
        first = self._stages[0]
        return RepairStageReceipt(attempt_id=attempt_id, stage=first, traversed=(first,))

    def advance(self, receipt: RepairStageReceipt, *, to_stage: str) -> RepairStageReceipt:
        """Refuse a skipped, reversed, repeated, unknown or off-path stage."""
        target = to_stage.strip().lower()
        try:
            current_index = self._stages.index(receipt.stage)
            target_index = self._stages.index(target)
        except ValueError as error:
            raise IllegalPipelineTransition(
                f"{to_stage!r} is not a stage in the governed failure protocol"
            ) from error
        if receipt.traversed != self._stages[: current_index + 1]:
            raise IllegalPipelineTransition(
                "stage receipt does not prove the complete governed prefix"
            )
        if target_index != current_index + 1:
            raise IllegalPipelineTransition(
                f"cannot advance from {receipt.stage!r} to {target!r}; "
                "every governed stage is required, in order"
            )
        return RepairStageReceipt(
            attempt_id=receipt.attempt_id,
            stage=target,
            traversed=(*receipt.traversed, target),
        )

    def is_terminal(self, receipt: RepairStageReceipt) -> bool:
        return receipt.stage == self._stages[-1]


class AttemptEvidence(BaseModel):
    """The two measured facts `Accept/Reject` is derived from. Never a status
    flag: there is no field here a caller could set to declare success."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    targeted_tests_passed: bool
    regression_passed: bool


class AttemptMeasurement(BaseModel):
    """What one attempt actually consumed, forwarded to
    `RepairBudgetLedger.record` unchanged. A separate value object rather
    than five more parameters on `resolve_attempt`, which would otherwise
    breach `max_parameters_per_public_function` (6) the way `record` itself
    already sits exactly at."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ai_calls: int = Field(ge=0)
    elapsed_seconds: int = Field(ge=0)
    cost: Decimal = Field(ge=0)
    touched_files: int = Field(ge=0)
    regression_delta: int = Field(ge=0)


def resolve_attempt(
    path: RepairPipelinePath,
    ledger: RepairBudgetLedger,
    receipt: RepairStageReceipt,
    fingerprint: RepairFingerprint,
    evidence: AttemptEvidence,
    measurement: AttemptMeasurement,
) -> RepairBudgetLedger:
    """Derive `Accept/Reject` from measured evidence and record it.

    Refuses to resolve an attempt that has not reached the governed terminal
    stage — an outcome recorded before `Targeted Tests` and `Regression`
    have run would not be evidence-driven, it would be a status string.
    `outcome` is DERIVED from `evidence`'s two facts, never accepted as a
    caller-declared verdict, so a failing attempt cannot be recorded as
    resolved by naming it so. Recording delegates entirely to
    `RepairBudgetLedger.record`, which enforces the six budget dimensions
    and the anti-loop refusal unchanged.
    """
    if not path.is_terminal(receipt):
        raise IllegalPipelineTransition(
            f"attempt {receipt.attempt_id!r} is at {receipt.stage!r}, not the "
            "governed terminal stage; Accept/Reject cannot be derived early"
        )
    outcome = (
        RESOLVED if (evidence.targeted_tests_passed and evidence.regression_passed)
        else REJECTED
    )
    resolved_fingerprint = fingerprint.model_copy(update={"outcome": outcome})
    return ledger.record(
        resolved_fingerprint,
        ai_calls=measurement.ai_calls,
        elapsed_seconds=measurement.elapsed_seconds,
        cost=measurement.cost,
        touched_files=measurement.touched_files,
        regression_delta=measurement.regression_delta,
    )
