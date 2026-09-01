"""The bounded Golden Repair convergence loop -- ARK-REQ-0092/0093/0094.

Owner: `engineering.repair`. Deliberately pure: no `engineering.candidate`
import here. The real `CandidateLedger`/`WorkspaceAuthority` lifecycle
orchestration that wraps this loop lives in `scripts/run_golden_repair.py`
(outside AUTHORITY_MAP.yaml's gated `backend/arkali` module tree) rather than
in this package, because exercising the already-declared `engineering.repair
-> engineering.candidate` sibling edge (AUTHORITY_MAP.yaml `allowed_sibling_
edges`: "repairs produce candidates") from inside a gated library module
pushes the real context-dependency graph's longest path past `max_
orchestration_depth` -- the same reason `run_staged_generation.py` and
`run_golden_acceptance.py` already keep their own `CandidateLedger`/
`WorkspaceAuthority` wiring in the script layer instead of a library module.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping

from arkali.engineering.repair.contracts import (
    RepairBudget,
    RepairBudgetLedger,
    RepairFingerprint,
)
from arkali.engineering.repair.errors import (
    RepairBudgetExceededError,
    RepeatedFailedStrategyError,
)
from arkali.engineering.repair.golden_corpus import RepairCorpusEntry
from arkali.engineering.repair.golden_corpus_injectors import DETECTORS


@dataclass(frozen=True)
class RepairRunResult:
    ledger: RepairBudgetLedger
    resolved: tuple[str, ...]
    escalated: tuple[str, ...]
    files: Mapping[str, str]


AttemptRepair = Callable[
    [RepairCorpusEntry, Mapping[str, str]],
    tuple["Mapping[str, str] | None", RepairFingerprint],
]


def _changed_file_count(before: Mapping[str, str], after: Mapping[str, str] | None) -> int:
    """The real number of paths one attempt actually touched -- added,
    removed, or content-changed -- never the size of the returned file set.
    `docs/contracts/repair.md`'s own "touched files" dimension names what a
    repair attempt changed, not what a candidate happens to contain; a real
    `attempt_repair` implementation that merges its proposal into the full
    current file set (returning all ~17 files of a real candidate on every
    attempt) must not be charged for the ~15+ files it left byte-identical.
    Same set-algebra idiom `changed_protected_paths` (`golden_corpus.py`)
    and `_manifest_diff` (`ledger.py`) already use -- not a new diff engine.
    An attempt that failed outright (`after is None`) touches nothing."""
    if after is None:
        return 0
    added_or_removed = set(before) ^ set(after)
    changed = {p for p in (set(before) & set(after)) if before[p] != after[p]}
    return len(added_or_removed) + len(changed)


def run_corpus_repair(
    entries: tuple[RepairCorpusEntry, ...],
    files: Mapping[str, str],
    budget: RepairBudget,
    attempt_repair: AttemptRepair,
    *,
    candidate_id: str,
) -> RepairRunResult:
    """Runs the WHOLE corpus's own bounded convergence loop in one call --
    the runner manages its own attempts/convergence internally (never
    relying on an operator re-invoking a process per attempt, which is what
    `run_golden_repair.py` did before this function existed). A repeated
    failed strategy or an exceeded budget dimension is the real, structural,
    automatic trigger for terminal ESCALATED (`RepeatedFailedStrategyError`/
    `RepairBudgetExceededError`, both already real in `contracts.py`) --
    never an operator-supplied flag.

    Budget enforcement is POST-consumption, by design (`docs/contracts/
    repair.md`: "Recording returns a new immutable ledger and refuses any
    candidate that would cross a ceiling") -- `attempt_repair` itself always
    runs first; only the resulting fingerprint's recording is refused. A
    real, already-doomed-by-budget attempt therefore still costs one real
    `attempt_repair` call; this is the documented contract, not a bug, and
    is left unchanged here.
    """
    ledger = RepairBudgetLedger(candidate_id=candidate_id, budget=budget)
    current: Mapping[str, str] = dict(files)
    resolved: list[str] = []
    escalated: list[str] = []
    for entry in sorted(entries, key=lambda e: e.id):
        detector = DETECTORS[entry.defect_class]
        while detector(current):
            started = time.monotonic()
            candidate_files, fingerprint = attempt_repair(entry, current)
            elapsed_seconds = max(0, math.ceil(time.monotonic() - started))
            try:
                ledger = ledger.record(
                    fingerprint,
                    ai_calls=1, elapsed_seconds=elapsed_seconds, cost=Decimal(0),
                    touched_files=_changed_file_count(current, candidate_files),
                    regression_delta=0,
                )
            except (RepeatedFailedStrategyError, RepairBudgetExceededError):
                escalated.append(entry.id)
                break
            if candidate_files is not None and not detector(candidate_files):
                current = dict(candidate_files)
                resolved.append(entry.id)
                break
        else:
            resolved.append(entry.id)
    return RepairRunResult(
        ledger=ledger, resolved=tuple(resolved), escalated=tuple(escalated), files=current,
    )


__all__ = ["AttemptRepair", "RepairRunResult", "run_corpus_repair"]
