"""Campaign-level budget and loop-control for `engineering.factory`'s golden
candidate generation runs (`run_staged_generation.py`).

Not the C-33 `lifecycle.evolution.campaign_ledger.CampaignLedger`: that
governs a different domain entirely (core-candidate self-upgrade campaigns,
ARK-REQ-0140/0141/0142, its own canonical state machine) and is never
imported by anything under `engineering.factory` or `engineering.candidate`.
This module is a distinct, purpose-built ledger for one narrower question:
across repeated golden-work generation attempts, when has the pipeline
proven it is going in circles rather than converging, and when must it stop
generating new candidates without a human looking at it first?

Root problem this closes: before this module, nothing in the staged-
generation pipeline placed any ceiling on how many `golden-work-N`
candidates could be allocated in a row, or noticed that the same failure
kept recurring. A budget-unaware loop can burn arbitrary time and compute
re-hitting one root cause under a new candidate_id each time.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from arkali.engineering.candidate.errors import (
    CampaignBudgetExhaustedError,
    CampaignEscalatedError,
)

DEFAULT_MAX_NEW_CANDIDATES = 5
#: 4 hours -- generous enough for several real staged-generation attempts
#: (golden-work-124 alone took ~66 minutes) without being unbounded.
DEFAULT_MAX_TOTAL_SECONDS = 14_400.0
#: A fingerprint may recur at most this many times before its NEXT
#: occurrence (the 3rd) escalates the campaign.
DEFAULT_MAX_SAME_FINGERPRINT_REPEATS = 2

#: A finding/error the checker itself misidentified -- not a real defect in
#: the generated candidate. Recorded only once a human (or a follow-up
#: investigation, as with golden-work-124's own call-side fix) has actually
#: confirmed the checker was wrong, never guessed automatically.
FALSE_POSITIVE_HARNESS_DEFECT = "false_positive_harness_defect"
#: The model produced a different, unrelated shape on this attempt -- not
#: the same root cause recurring, just normal sampling variance.
MODEL_VARIANCE = "model_variance"
#: A real, correctly-identified defect in what the model generated.
CANDIDATE_DEFECT = "candidate_defect"
#: The run failed for a reason outside the model's or checker's control --
#: a crashed dependency, a network timeout, disk exhaustion, and similar.
INFRASTRUCTURE_FAILURE = "infrastructure_failure"

FAILURE_CLASSES = frozenset({
    FALSE_POSITIVE_HARNESS_DEFECT, MODEL_VARIANCE, CANDIDATE_DEFECT, INFRASTRUCTURE_FAILURE,
})

CAMPAIGN_RUNNING = "CAMPAIGN_RUNNING"
CAMPAIGN_BUDGET_EXHAUSTED = "CAMPAIGN_BUDGET_EXHAUSTED"
CAMPAIGN_ESCALATED = "CAMPAIGN_ESCALATED"

_STAGE_FAILURE_FINGERPRINT = re.compile(
    r"stage '(?P<stage>[^']+)' exhausted \d+ attempts: (?P<finding>[a-z0-9_]+)"
)


def fingerprint_of(outcome: str, error_message: str) -> str:
    """A short, stable label for "what kind of failure was this", derived
    from the pipeline's own error text rather than guessed: a staged-
    generation failure's message already names the stage and the first
    blocking finding code (`[ARK-ERR-0116] stage 'frontend_forms'
    exhausted 4 attempts: frontend_ui_missing_edit_ui:...`, golden-work-
    124's own real error). Falls back to `f"{outcome}:{error_message}"`
    verbatim for any shape that pattern does not match, so every failure
    still gets a fingerprint, just a coarser one."""
    match = _STAGE_FAILURE_FINGERPRINT.search(error_message)
    if match:
        return f"{outcome}:{match.group('stage')}:{match.group('finding')}"
    return f"{outcome}:{error_message}"


@dataclass(frozen=True)
class CampaignBudget:
    max_new_candidates: int = DEFAULT_MAX_NEW_CANDIDATES
    max_total_seconds: float = DEFAULT_MAX_TOTAL_SECONDS
    max_same_fingerprint_repeats: int = DEFAULT_MAX_SAME_FINGERPRINT_REPEATS

    def as_dict(self) -> dict[str, object]:
        return {
            "max_new_candidates": self.max_new_candidates,
            "max_total_seconds": self.max_total_seconds,
            "max_same_fingerprint_repeats": self.max_same_fingerprint_repeats,
        }


class GenerationCampaignLedger:
    """One campaign's durable, append-only record of every candidate
    attempt. Persisted as `ledger.jsonl` under the campaign's own root --
    loading it back (`load_or_create`) re-derives the SAME consumption a
    fresh process would have seen, so a new Claude session, a new
    terminal, or a restarted script never silently resets the budget.
    The first line is the campaign's own declared budget, written once;
    every later line is one candidate's recorded outcome.
    """

    def __init__(self, campaign_id: str, budget: CampaignBudget, root: pathlib.Path) -> None:
        self.campaign_id = campaign_id
        self.budget = budget
        self._root = root
        self._log = root / "ledger.jsonl"
        self._attempts: list[dict[str, object]] = []

    @classmethod
    def load_or_create(
        cls, campaigns_root: pathlib.Path, campaign_id: str, default_budget: CampaignBudget,
    ) -> GenerationCampaignLedger:
        """Loads the existing campaign at `campaigns_root/campaign_id` if
        one is already on disk -- consumption AND the originally declared
        budget both come from that file, never from `default_budget` --
        or creates a new one declaring `default_budget` if this is the
        first time this `campaign_id` has been used."""
        root = campaigns_root / campaign_id
        root.mkdir(parents=True, exist_ok=True)
        log = root / "ledger.jsonl"
        if not log.exists():
            ledger = cls(campaign_id, default_budget, root)
            ledger._append({
                "kind": "DECLARED", "campaign_id": campaign_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "budget": default_budget.as_dict(),
            })
            return ledger
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        declared = lines[0]
        budget = CampaignBudget(**declared["budget"])
        ledger = cls(campaign_id, budget, root)
        ledger._attempts = lines[1:]
        return ledger

    def _append(self, entry: dict[str, object]) -> None:
        with self._log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    @property
    def consumed_candidates(self) -> int:
        return len(self._attempts)

    @property
    def consumed_seconds(self) -> float:
        return sum(float(a["elapsed_seconds"]) for a in self._attempts)

    def fingerprint_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for attempt in self._attempts:
            fp = attempt.get("fingerprint")
            if fp:
                counts[str(fp)] = counts.get(str(fp), 0) + 1
        return counts

    def escalated_fingerprint(self) -> str | None:
        """The fingerprint that has already recurred `max_same_
        fingerprint_repeats` times, if any -- its NEXT occurrence is the
        one that would escalate the campaign."""
        for fingerprint, count in self.fingerprint_counts().items():
            if count > self.budget.max_same_fingerprint_repeats:
                return fingerprint
        return None

    def status(self) -> str:
        if self.escalated_fingerprint() is not None:
            return CAMPAIGN_ESCALATED
        if (
            self.consumed_candidates >= self.budget.max_new_candidates
            or self.consumed_seconds >= self.budget.max_total_seconds
        ):
            return CAMPAIGN_BUDGET_EXHAUSTED
        return CAMPAIGN_RUNNING

    def refuse_new_candidate_unless_permitted(self, *, override_confirmed: bool) -> None:
        """Call before allocating a new candidate. Escalation refuses
        outright, override or not -- a recurring root cause needs a human
        to look at it, not a bigger budget. A merely exhausted budget
        (candidate count or elapsed time) refuses UNLESS the caller passes
        `override_confirmed=True`, which a script may only set from an
        explicit user-facing confirmation (a CLI flag the operator typed
        themselves), never a default."""
        state = self.status()
        if state == CAMPAIGN_ESCALATED:
            fingerprint = self.escalated_fingerprint()
            raise CampaignEscalatedError(
                f"CAMPAIGN_ESCALATED: fingerprint {fingerprint!r} has recurred "
                f"{self.budget.max_same_fingerprint_repeats} times in campaign "
                f"{self.campaign_id!r}; no further candidates without human review"
            )
        if state == CAMPAIGN_BUDGET_EXHAUSTED and not override_confirmed:
            raise CampaignBudgetExhaustedError(
                f"campaign {self.campaign_id!r} budget exhausted "
                f"(candidates={self.consumed_candidates}/{self.budget.max_new_candidates}, "
                f"seconds={self.consumed_seconds:.1f}/{self.budget.max_total_seconds:.1f}); "
                "a new candidate requires an explicit, human-confirmed override"
            )

    def record(
        self,
        candidate_id: str,
        outcome: str,
        *,
        elapsed_seconds: float,
        failure_class: str | None = None,
        error_message: str = "",
        detail: Mapping[str, object] | None = None,
    ) -> None:
        """Records one candidate's real result. Always allowed to record
        (an outcome that itself triggers escalation must still be
        written, or the ledger could never observe the 3rd recurrence);
        only STARTING a new candidate is gated, via
        `refuse_new_candidate_unless_permitted`."""
        if failure_class is not None and failure_class not in FAILURE_CLASSES:
            raise ValueError(f"unknown failure_class: {failure_class!r}")
        fingerprint = fingerprint_of(outcome, error_message) if error_message else None
        entry = {
            "kind": "ATTEMPT",
            "candidate_id": candidate_id,
            "outcome": outcome,
            "elapsed_seconds": elapsed_seconds,
            "failure_class": failure_class,
            "fingerprint": fingerprint,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "detail": dict(detail) if detail else {},
        }
        self._attempts.append(entry)
        self._append(entry)


__all__ = [
    "CAMPAIGN_BUDGET_EXHAUSTED",
    "CAMPAIGN_ESCALATED",
    "CAMPAIGN_RUNNING",
    "CANDIDATE_DEFECT",
    "CampaignBudget",
    "DEFAULT_MAX_NEW_CANDIDATES",
    "DEFAULT_MAX_SAME_FINGERPRINT_REPEATS",
    "DEFAULT_MAX_TOTAL_SECONDS",
    "FALSE_POSITIVE_HARNESS_DEFECT",
    "FAILURE_CLASSES",
    "GenerationCampaignLedger",
    "INFRASTRUCTURE_FAILURE",
    "MODEL_VARIANCE",
    "fingerprint_of",
]
