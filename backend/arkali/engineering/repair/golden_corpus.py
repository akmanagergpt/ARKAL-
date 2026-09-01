"""Golden Repair defect corpus: canonical schema, corpus-instance loading,
and the no-test-weakening comparison helper.

The 8 canonical injector/detector pairs live in `golden_corpus_injectors.py`,
and the bounded repair-convergence loop and lifecycle orchestration live in
`golden_repair_runner.py` -- both split out of this module to keep each
file's own real size and this context's total public surface within
AUTHORITY_MAP.yaml's architecture budgets. This module is the one every
other Golden Repair module imports FROM (schema first); it imports from
neither of them, so the three-file split stays acyclic.

Owner: `engineering.repair`. Implements `docs/canonical/GOLDEN_REPAIR_CORPUS_
DEFINITION.md` (Phase 0B's corpus DEFINITION) at Phase 30 (corpus
INSTANTIATION) -- the schema, the 8 canonical defect classes, the versioning/
hashing rule and the injection contract are restated from that document, not
redefined: `ARK-REQ-0187`/`0188`.
"""

from __future__ import annotations

import pathlib
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

from arkali.engineering.repair.contracts import content_hash

#: The eight canonical defect classes (GOLDEN_REPAIR_CORPUS_DEFINITION.md
#: §2) -- restated here as the closed vocabulary a `RepairCorpusEntry` may
#: declare, the same shape `campaign_budget.FAILURE_CLASSES` already uses
#: for a comparably small, stable, canonical-document-sourced vocabulary.
CONTRACT_VIOLATION = "contract_violation"
STATE_MACHINE_INVALID_TRANSITION = "state_machine_invalid_transition"
PERMISSION_CHECK_REMOVAL = "permission_check_removal"
PERSISTENCE_NOT_COMMITTED = "persistence_not_committed"
API_FRONTEND_CONTRACT_DRIFT = "api_frontend_contract_drift"
DEPENDENCY_LOCK_MISMATCH = "dependency_lock_mismatch"
MIGRATION_MODEL_MISMATCH = "migration_model_mismatch"
BOUNDARY_OFF_BY_ONE = "boundary_off_by_one"

DEFECT_CLASSES: tuple[str, ...] = (
    CONTRACT_VIOLATION,
    STATE_MACHINE_INVALID_TRANSITION,
    PERMISSION_CHECK_REMOVAL,
    PERSISTENCE_NOT_COMMITTED,
    API_FRONTEND_CONTRACT_DRIFT,
    DEPENDENCY_LOCK_MISMATCH,
    MIGRATION_MODEL_MISMATCH,
    BOUNDARY_OFF_BY_ONE,
)


class CorpusInjectionError(Exception):
    """An injector found no real structural target for its declared class in
    these files -- refuses rather than fabricating one (the same posture
    `_AcceptancePlanIncomplete` already takes for the acceptance side)."""


class RepairCorpusEntry(BaseModel):
    """One real corpus entry, matching `GOLDEN_REPAIR_CORPUS_DEFINITION.md`
    §1's schema field-for-field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    defect_class: str
    title: str = Field(min_length=1)
    injection_target: str
    injection_strategy: str = Field(min_length=1)
    expected_detection: tuple[str, ...] = Field(min_length=1)
    repairable: bool
    budget_profile: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    def rendering(self) -> bytes:
        import json
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


def corpus_hash(entries: tuple[RepairCorpusEntry, ...]) -> str:
    """Corpus definition §3: content-hashed over the canonical serialisation
    of all entries, sorted by id."""
    import json
    ordered = sorted(entries, key=lambda e: e.id)
    payload = json.dumps(
        [e.model_dump(mode="json") for e in ordered],
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return content_hash(payload)


def load_corpus_instance(path: pathlib.Path) -> tuple[RepairCorpusEntry, ...]:
    """Loads a real, versioned corpus instantiation (`golden/repair/golden_
    repair_corpus.json`, matching the real-data-file pattern this repository
    already uses for its acceptance-side scenario fixtures under `golden/`
    -- never a second corpus authority in code). Refuses a corpus missing
    any of the 8 canonical classes (corpus definition §2: "may never
    contain fewer") or missing the mandatory unrepairable entry (§4)."""
    import json
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = tuple(
        RepairCorpusEntry.model_validate(item) for item in payload["entries"]
    )
    missing = set(DEFECT_CLASSES) - {e.defect_class for e in entries}
    if missing:
        raise CorpusInjectionError(f"corpus instance is missing required classes: {sorted(missing)}")
    if not any(not e.repairable for e in entries):
        raise CorpusInjectionError("corpus instance has no mandatory unrepairable entry (§4)")
    return entries


#: Paths a real repair (and a real injection, per corpus definition §5.4)
#: may never change -- ARK-REQ-0093's "no acceptance test weakened, deleted
#: or rewritten during repair".
PROTECTED_PATH_PREFIXES: tuple[str, ...] = ("tests/", "config/")


def changed_protected_paths(
    parent_manifest: Mapping[str, Mapping[str, object]],
    child_manifest: Mapping[str, Mapping[str, object]],
    *,
    prefixes: tuple[str, ...] = PROTECTED_PATH_PREFIXES,
) -> tuple[str, ...]:
    """Real, mechanical proof of ARK-REQ-0093's no-test-weakening condition.

    REUSES `CandidateLedger.file_manifest()`'s own existing per-file sha256
    output (already computed once at the parent's own accepted state, and
    once for the repair child) -- never a second hashing mechanism. Any
    added, removed, or changed path under `prefixes` is returned; an empty
    result is the only honest proof that repair (and injection before it)
    never touched a protected path.
    """
    parent_protected = {p: v for p, v in parent_manifest.items() if p.startswith(prefixes)}
    child_protected = {p: v for p, v in child_manifest.items() if p.startswith(prefixes)}
    all_paths = set(parent_protected) | set(child_protected)
    unchanged = {
        p for p in (set(parent_protected) & set(child_protected))
        if parent_protected[p] == child_protected[p]
    }
    return tuple(sorted(all_paths - unchanged))


__all__ = [
    "API_FRONTEND_CONTRACT_DRIFT",
    "BOUNDARY_OFF_BY_ONE",
    "CONTRACT_VIOLATION",
    "CorpusInjectionError",
    "DEFECT_CLASSES",
    "DEPENDENCY_LOCK_MISMATCH",
    "MIGRATION_MODEL_MISMATCH",
    "PERMISSION_CHECK_REMOVAL",
    "PERSISTENCE_NOT_COMMITTED",
    "PROTECTED_PATH_PREFIXES",
    "RepairCorpusEntry",
    "STATE_MACHINE_INVALID_TRANSITION",
    "changed_protected_paths",
    "corpus_hash",
    "load_corpus_instance",
]
