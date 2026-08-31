"""Durable identity, lifecycle, and tamper-evidence ledger for `engineering.
factory`'s staged-generation candidates (`golden-work-*` directories under
`var/factory/candidates/`).

Not the C-25 canonical `Candidate` state machine (`candidate_state_machine.
py`) or its `CandidateManifest` (`manifest.py`): those govern the Product
Plane component-assembly path (`assembly.py`, ADR/Phase 12) and are wired
into a different pipeline entirely -- `run_staged_generation.py` and
`WorkspaceAuthority` never touch them. This module is the staged-generation
pipeline's own bookkeeping, not a second implementation of that machine.

golden-work-124 (real repository evidence): `WorkspaceAuthority.allocate`
refuses a *directory* collision (`root.mkdir(..., exist_ok=False)`), but has
no memory beyond the filesystem -- delete the directory and the same
`workspace_id` is allocatable again, with no link back to whatever the
identity previously meant. Investigating why a stale session's account of
golden-work-124 (a `StudentEdit.js` missing a `useParams` import) did not
match the live candidate directory (no such file) showed the real cause was
not corruption at all: `frontend_forms` exhausted all 4 attempts and never
passed, so `generate_staged_model_product`'s own write-only-after-validation
rule (`component_generation.py`) correctly never wrote that stage's files to
the workspace -- the `StudentEdit.js` in question was the *last failed
attempt's* raw output, captured only in `var/factory/evidence`'s
content-addressed blob store (`repair-evidence.db` `artifact_provenance`,
`recorded_at` 2026-08-25T05:21:57Z, evidence `["real staged-generation stage
failure"]`), never promoted into the candidate tree. The system behaved
correctly. But nothing would have caught it if it hadn't: no ledger recorded
that `golden-work-124` had ever existed once its directory existed, no
manifest pinned what its terminal content should be, and nothing would have
refused a second, unrelated generation run reusing that same identity had
the directory ever been deleted. This module closes that gap.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

from arkali.engineering.candidate.errors import (
    CandidateAcceptanceInProgressError,
    CandidateIdentityReuseError,
    CandidateIntegrityError,
    InvalidLifecycleTransitionError,
    UnknownLifecycleStateError,
)

#: Non-terminal: a candidate_id has been reserved (identity exists) but no
#: workspace write has happened yet.
ALLOCATED = "ALLOCATED"
#: Non-terminal: staged generation is actively running. A candidate whose
#: latest recorded state is GENERATING with no later entry is *recoverable*
#: (its process may simply still be running) rather than failed outright --
#: only an explicit terminal state, or a caller's own liveness check against
#: the process that was generating it, can resolve that ambiguity further.
GENERATING = "GENERATING"
#: Terminal: a stage exhausted its attempt budget; nothing from that stage
#: was written to the workspace.
STAGE_FAILED = "STAGE_FAILED"
#: Terminal: every stage wrote real files, but the assembled whole-product
#: gate (`product_preflight.inspect_product_files`) refused them.
FINAL_GATE_FAILED = "FINAL_GATE_FAILED"
#: Generation-terminal, but NOT lifecycle-terminal: staged generation and
#: the whole-product gate both passed. This is the ONLY state acceptance
#: may begin from (`begin_acceptance`) -- its one permitted transition is
#: to ACCEPTANCE_RUNNING. Not itself an acceptance verdict.
STAGED_GENERATION_PASS = "STAGED_GENERATION_PASS"
#: Non-terminal: `run_golden_acceptance.py`'s real journey is actively
#: running. Entered only via `begin_acceptance`, which locks and verifies
#: atomically -- a second concurrent attempt for the same candidate_id is
#: refused outright, never silently queued. The same hard-kill caveat as
#: GENERATING applies: a process killed mid-acceptance leaves this as the
#: last recorded state, requiring a human/reconciling caller to decide,
#: never an automatic retry.
ACCEPTANCE_RUNNING = "ACCEPTANCE_RUNNING"
#: Terminal: `run_golden_acceptance.py`'s real journey failed a classified
#: check (`Journey.record`, `AcceptanceCheckFailed`).
ACCEPTANCE_FAILED = "ACCEPTANCE_FAILED"
#: Terminal: `run_golden_acceptance.py`'s real journey passed in full. No
#: further transition exists -- an ACCEPTED candidate can never re-enter
#: acceptance.
ACCEPTED = "ACCEPTED"
#: Terminal: the run ended without reaching any of the above -- a caught
#: `KeyboardInterrupt`, or (during acceptance specifically) any exception
#: that was not a classified `AcceptanceCheckFailed`. A hard process kill
#: (SIGKILL / taskkill) cannot run this handler at all; such a run's last
#: recorded state stays GENERATING or ACCEPTANCE_RUNNING, which a
#: reconciling caller must treat as recoverable/unknown, never silently
#: as failure or success.
INTERRUPTED = "INTERRUPTED"

#: Every state with zero permitted outgoing transitions -- once recorded,
#: nothing further may ever be recorded for that candidate_id.
TERMINAL_STATES = frozenset({
    STAGE_FAILED, FINAL_GATE_FAILED, ACCEPTANCE_FAILED, ACCEPTED, INTERRUPTED,
})
ALL_STATES = frozenset({ALLOCATED, GENERATING, STAGED_GENERATION_PASS, ACCEPTANCE_RUNNING}) | TERMINAL_STATES

#: The complete lifecycle graph. `record_state` (and `begin_acceptance`,
#: which calls it) refuses any transition not listed here for the
#: candidate's current latest state -- this is what makes
#: STAGED_GENERATION_PASS -> ACCEPTANCE_RUNNING -> {ACCEPTED,
#: ACCEPTANCE_FAILED, INTERRUPTED} the only path acceptance can ever take,
#: and what makes STAGE_FAILED, FINAL_GATE_FAILED, ACCEPTANCE_FAILED,
#: ACCEPTED, and INTERRUPTED true dead ends.
_TRANSITIONS: dict[str, frozenset[str]] = {
    ALLOCATED: frozenset({GENERATING}),
    GENERATING: frozenset({STAGE_FAILED, FINAL_GATE_FAILED, STAGED_GENERATION_PASS, INTERRUPTED}),
    STAGED_GENERATION_PASS: frozenset({ACCEPTANCE_RUNNING}),
    ACCEPTANCE_RUNNING: frozenset({ACCEPTED, ACCEPTANCE_FAILED, INTERRUPTED}),
    STAGE_FAILED: frozenset(),
    FINAL_GATE_FAILED: frozenset(),
    ACCEPTANCE_FAILED: frozenset(),
    ACCEPTED: frozenset(),
    INTERRUPTED: frozenset(),
}
#: States with a real, frozen, verifiable manifest -- everything except
#: the three "actively in flight, nothing final written yet" states.
#: Broader than `TERMINAL_STATES ` (adds STAGED_GENERATION_PASS): used by
#: the general-purpose `verify_integrity`, not by the strict acceptance
#: gate (`begin_acceptance`, which only ever accepts STAGED_GENERATION_PASS).
_VERIFIABLE_STATES = ALL_STATES - {ALLOCATED, GENERATING, ACCEPTANCE_RUNNING}

#: A pre-existing candidate directory this ledger has no history for at all.
#: Never upgraded to a verified state retroactively -- absence of evidence
#: is recorded as its own honest classification, not asserted as a pass.
LEGACY_UNVERIFIED = "LEGACY_UNVERIFIED"

_SNAPSHOT_DIR_NAME = "snapshot"


@dataclass(frozen=True)
class GenerationProvenance:
    """Everything needed to answer "what, exactly, produced this candidate"
    without re-deriving it from logs: the goal it was generated against, the
    source revision of the pipeline itself, and the exact model/runtime
    configuration used."""

    goal_hash: str
    source_commit: str
    runtime: str
    endpoint: str
    model: str
    model_parameters: Mapping[str, object] = field(default_factory=dict)
    pipeline_version: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "goal_hash": self.goal_hash,
            "source_commit": self.source_commit,
            "runtime": self.runtime,
            "endpoint": self.endpoint,
            "model": self.model,
            "model_parameters": dict(self.model_parameters),
            "pipeline_version": self.pipeline_version,
        }


def hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_manifest(root: pathlib.Path) -> dict[str, dict[str, object]]:
    """Every real file under `root` (excluding the pre-populated stable
    `snapshot/` subtree, which is baseline scaffolding the model never
    wrote) as `{relative_posix_path: {"byte_length": int, "sha256": hex}}`.
    Sorted-path iteration makes the result deterministic across platforms
    and across repeated calls against the same content.

    Walked with `os.walk(..., followlinks=False)` and an explicit
    per-file `is_symlink()` check, deliberately not `Path.rglob` (which
    follows symlinks): a model-generated candidate is untrusted content,
    and a symlink inside it -- file or directory -- pointing outside
    `root` must never be traversed into or hashed, the same containment
    `WorkspaceAuthority.write` already enforces on the write side.
    """
    manifest: dict[str, dict[str, object]] = {}
    if not root.is_dir():
        return manifest
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = pathlib.Path(dirpath)
        if current == root:
            dirnames[:] = [d for d in dirnames if d != _SNAPSHOT_DIR_NAME]
        dirnames[:] = [d for d in dirnames if not (current / d).is_symlink()]
        for name in filenames:
            path = current / name
            if path.is_symlink():
                continue
            relative = path.relative_to(root)
            data = path.read_bytes()
            manifest[relative.as_posix()] = {
                "byte_length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
    return manifest


def _manifest_diff(
    recorded: Mapping[str, Mapping[str, object]], live: Mapping[str, Mapping[str, object]],
) -> dict[str, list[str]]:
    return {
        "added": sorted(set(live) - set(recorded)),
        "removed": sorted(set(recorded) - set(live)),
        "changed": sorted(p for p in (set(live) & set(recorded)) if live[p] != recorded[p]),
    }


class CandidateLedger:
    """Append-only, per-root JSON-lines identity and lifecycle record.

    Every `allocate`/`record_state` call appends one immutable line to
    `ledger.jsonl`; nothing already written is ever rewritten or removed.
    The ledger, not the filesystem, is the authority on "has this
    candidate_id ever existed" -- `latest()`/`history()` still answer that
    correctly after a workspace directory is deleted.
    """

    def __init__(self, ledger_root: pathlib.Path) -> None:
        self._root = ledger_root
        self._root.mkdir(parents=True, exist_ok=True)
        self._log = self._root / "ledger.jsonl"

    def history(self, candidate_id: str) -> tuple[dict[str, object], ...]:
        if not self._log.exists():
            return ()
        entries = []
        for line in self._log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry["candidate_id"] == candidate_id:
                entries.append(entry)
        return tuple(entries)

    def all_candidate_ids(self) -> tuple[str, ...]:
        """Every real candidate_id this ledger has ever recorded, in first-
        appearance order -- the ledger, not the filesystem, is authoritative
        (the same posture `history`/`classify` already take), so a deleted
        workspace directory still appears here."""
        if not self._log.exists():
            return ()
        seen: dict[str, None] = {}
        for line in self._log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            seen.setdefault(str(entry["candidate_id"]), None)
        return tuple(seen)

    def latest(self, candidate_id: str) -> dict[str, object] | None:
        entries = self.history(candidate_id)
        return entries[-1] if entries else None

    def classify(self, candidate_id: str) -> str:
        """The most honest single label for this identity right now:
        `LEGACY_UNVERIFIED` if the ledger has no history for it at all
        (never retroactively promoted to a verified state), otherwise its
        latest recorded lifecycle state."""
        latest = self.latest(candidate_id)
        return LEGACY_UNVERIFIED if latest is None else str(latest["state"])

    def accepted_candidate_for_goal(self, goal_hash: str) -> str | None:
        """The first real candidate_id whose own recorded `goal_hash`
        (its ALLOCATED entry's `GenerationProvenance.goal_hash`, the
        existing authoritative goal identity this ledger already carries
        per candidate -- never a second, parallel identity) equals
        `goal_hash` AND whose latest recorded lifecycle state is exactly
        `ACCEPTED`. `None` for a fresh goal, or a goal whose every
        candidate so far failed, was interrupted, or never finished --
        those are legitimately re-generatable.

        Reads only this ledger's own real, append-only entries. A goal's
        acceptance is never inferred from prose, a docstring, a file name,
        or any state held anywhere else -- only a real terminal `ACCEPTED`
        entry, recorded by `run_golden_acceptance.py`'s own real journey,
        counts.
        """
        for candidate_id in self.all_candidate_ids():
            entries = self.history(candidate_id)
            if not entries or str(entries[0].get("goal_hash", "")) != goal_hash:
                continue
            if str(entries[-1]["state"]) == ACCEPTED:
                return candidate_id
        return None

    def _append(self, entry: dict[str, object]) -> None:
        with self._log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def allocate(self, candidate_id: str, *, provenance: GenerationProvenance) -> None:
        """Record `ALLOCATED`. Refuses outright if `candidate_id` has EVER
        appeared in this ledger, regardless of whether a workspace
        directory for it currently exists on disk."""
        if self.history(candidate_id):
            raise CandidateIdentityReuseError(
                f"candidate_id {candidate_id!r} already has ledger history; identities "
                "are never reused, even if the workspace directory was deleted"
            )
        self._append({
            "candidate_id": candidate_id,
            "state": ALLOCATED,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "manifest": None,
            "detail": {},
            **provenance.as_dict(),
        })

    def record_state(
        self,
        candidate_id: str,
        state: str,
        workspace_root: pathlib.Path,
        *,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        """Append one lifecycle entry, capturing the live file manifest of
        `workspace_root` at this moment. Refuses a state outside
        `ALL_STATES`, refuses recording anything at all for an identity
        this ledger never allocated, and -- the real defect a STAGE_FAILED
        candidate previously passing `verify_integrity` exposed -- refuses
        any transition `_TRANSITIONS` does not list for the candidate's
        current latest state. A dead-end state (STAGE_FAILED, FINAL_GATE_
        FAILED, ACCEPTANCE_FAILED, ACCEPTED, INTERRUPTED) permits nothing
        further at all."""
        if state not in ALL_STATES:
            raise UnknownLifecycleStateError(f"unknown candidate lifecycle state: {state!r}")
        latest = self.latest(candidate_id)
        if latest is None:
            raise CandidateIdentityReuseError(
                f"candidate_id {candidate_id!r} was never allocated in this ledger"
            )
        current_state = str(latest["state"])
        if state not in _TRANSITIONS.get(current_state, frozenset()):
            raise InvalidLifecycleTransitionError(
                f"candidate_id {candidate_id!r} cannot transition from {current_state!r} "
                f"to {state!r}"
            )
        self._append({
            "candidate_id": candidate_id,
            "state": state,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "manifest": file_manifest(workspace_root),
            "detail": dict(detail) if detail else {},
        })

    def verify_integrity(self, candidate_id: str, workspace_root: pathlib.Path) -> None:
        """Recomputes `workspace_root`'s live manifest and compares it,
        file-for-file, against the manifest recorded at this candidate's
        last recorded state, for any state with a real frozen manifest
        (`_VERIFIABLE_STATES` -- everything except ALLOCATED, GENERATING,
        and ACCEPTANCE_RUNNING, which have nothing final to compare
        against yet). Raises `CandidateIntegrityError` on any difference
        -- an added file, a removed file, or changed bytes. A general-
        purpose read-only check; `begin_acceptance` is the strict gate
        that decides whether acceptance specifically may start (only ever
        from STAGED_GENERATION_PASS, never from any other verifiable
        state such as STAGE_FAILED)."""
        latest = self.latest(candidate_id)
        if latest is None or latest["state"] not in _VERIFIABLE_STATES or latest["manifest"] is None:
            raise CandidateIntegrityError(
                f"CANDIDATE_INTEGRITY_FAILED: {candidate_id!r} has no recorded, verifiable "
                "manifest (never allocated in this ledger, still in flight, or "
                "legacy/unverified)"
            )
        recorded = latest["manifest"]
        live = file_manifest(workspace_root)
        if recorded != live:
            diff = _manifest_diff(recorded, live)
            raise CandidateIntegrityError(
                f"CANDIDATE_INTEGRITY_FAILED: {candidate_id!r} no longer matches its "
                f"recorded manifest -- added={diff['added']} removed={diff['removed']} "
                f"changed={diff['changed']}"
            )

    def begin_acceptance(self, candidate_id: str, workspace_root: pathlib.Path) -> None:
        """The strict, atomic gate for starting real acceptance
        (`run_golden_acceptance.py`). Combines three checks that must all
        happen as one indivisible operation -- eligibility (latest
        recorded state must be exactly STAGED_GENERATION_PASS; a
        STAGE_FAILED or already-ACCEPTED candidate is refused just as
        surely as a tampered one), integrity (live content must match the
        manifest recorded at that STAGED_GENERATION_PASS state), and the
        ACCEPTANCE_RUNNING transition itself -- behind one atomic,
        cross-platform file lock (`os.O_CREAT | os.O_EXCL`, portable to
        both Windows and POSIX) keyed on `candidate_id`. A second caller
        for the same candidate_id while the first holds the lock is
        refused outright with `CandidateAcceptanceInProgressError`, never
        silently queued or allowed to race the eligibility check. The
        lock is held only for this check-and-transition, not for the
        whole acceptance run -- once ACCEPTANCE_RUNNING is recorded, that
        recorded state itself is what refuses a third concurrent
        attempt (no further transition exists FROM STAGED_GENERATION_PASS
        once it has already moved to ACCEPTANCE_RUNNING).

        A process killed hard between acquiring this lock and its
        `finally` releasing it leaves a stale lock file that permanently
        refuses further attempts for this candidate_id until an operator
        removes it by hand -- the same honest, no-automatic-recovery
        stance already documented for a hard-killed GENERATING run.
        """
        lock_path = self._root / f"{candidate_id}.acceptance.lock"
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError as exc:
            raise CandidateAcceptanceInProgressError(
                f"candidate_id {candidate_id!r} already has an acceptance attempt "
                "starting or in progress; concurrent acceptance runs on the same "
                "candidate are refused"
            ) from exc
        try:
            latest = self.latest(candidate_id)
            current_state = LEGACY_UNVERIFIED if latest is None else str(latest["state"])
            if current_state != STAGED_GENERATION_PASS:
                raise CandidateIntegrityError(
                    f"CANDIDATE_INTEGRITY_FAILED: {candidate_id!r} is not acceptance-"
                    f"eligible (latest recorded state: {current_state!r}; acceptance "
                    f"only ever begins from {STAGED_GENERATION_PASS!r})"
                )
            recorded = latest["manifest"]
            live = file_manifest(workspace_root)
            if recorded != live:
                diff = _manifest_diff(recorded, live)
                raise CandidateIntegrityError(
                    f"CANDIDATE_INTEGRITY_FAILED: {candidate_id!r} no longer matches "
                    f"its recorded manifest -- added={diff['added']} "
                    f"removed={diff['removed']} changed={diff['changed']}"
                )
            self.record_state(candidate_id, ACCEPTANCE_RUNNING, workspace_root)
        finally:
            lock_path.unlink(missing_ok=True)


__all__ = [
    "ALL_STATES",
    "ALLOCATED",
    "ACCEPTANCE_FAILED",
    "ACCEPTANCE_RUNNING",
    "ACCEPTED",
    "CandidateAcceptanceInProgressError",
    "CandidateIdentityReuseError",
    "CandidateIntegrityError",
    "CandidateLedger",
    "FINAL_GATE_FAILED",
    "GENERATING",
    "GenerationProvenance",
    "INTERRUPTED",
    "InvalidLifecycleTransitionError",
    "LEGACY_UNVERIFIED",
    "STAGED_GENERATION_PASS",
    "STAGE_FAILED",
    "TERMINAL_STATES",
    "UnknownLifecycleStateError",
    "file_manifest",
    "hash_text",
]
