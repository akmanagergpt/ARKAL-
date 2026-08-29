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
    CandidateIdentityReuseError,
    CandidateIntegrityError,
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
#: Terminal: staged generation and the whole-product gate both passed. Not
#: itself an acceptance verdict -- acceptance is a separate, later stage.
STAGED_GENERATION_PASS = "STAGED_GENERATION_PASS"
#: Terminal: `run_golden_acceptance.py`'s real journey failed.
ACCEPTANCE_FAILED = "ACCEPTANCE_FAILED"
#: Terminal: `run_golden_acceptance.py`'s real journey passed in full.
ACCEPTED = "ACCEPTED"
#: Terminal: the run ended without reaching any of the above -- a caught
#: `KeyboardInterrupt` or an exception the pipeline did not already classify.
#: A hard process kill (SIGKILL / taskkill) cannot run this handler at all;
#: such a run's last recorded state stays GENERATING, which a reconciling
#: caller must treat as recoverable/unknown, not silently as failure.
INTERRUPTED = "INTERRUPTED"

TERMINAL_STATES = frozenset({
    STAGE_FAILED, FINAL_GATE_FAILED, STAGED_GENERATION_PASS,
    ACCEPTANCE_FAILED, ACCEPTED, INTERRUPTED,
})
ALL_STATES = frozenset({ALLOCATED, GENERATING}) | TERMINAL_STATES

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
        `ALL_STATES`, and refuses recording anything at all for an
        identity this ledger never allocated."""
        if state not in ALL_STATES:
            raise UnknownLifecycleStateError(f"unknown candidate lifecycle state: {state!r}")
        if not self.history(candidate_id):
            raise CandidateIdentityReuseError(
                f"candidate_id {candidate_id!r} was never allocated in this ledger"
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
        last terminal state. Raises `CandidateIntegrityError` on any
        difference -- an added file, a removed file, or changed bytes --
        rather than letting a caller (acceptance, in particular) proceed
        against silently modified content. Raises the same error if there
        is no recorded terminal manifest to verify against at all (a
        `LEGACY_UNVERIFIED` candidate, or one still mid-generation)."""
        latest = self.latest(candidate_id)
        if latest is None or latest["state"] not in TERMINAL_STATES or latest["manifest"] is None:
            raise CandidateIntegrityError(
                f"CANDIDATE_INTEGRITY_FAILED: {candidate_id!r} has no recorded terminal "
                "manifest to verify against (never allocated in this ledger, still "
                "generating, or legacy/unverified)"
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


__all__ = [
    "ALL_STATES",
    "ALLOCATED",
    "ACCEPTANCE_FAILED",
    "ACCEPTED",
    "CandidateIdentityReuseError",
    "CandidateIntegrityError",
    "CandidateLedger",
    "FINAL_GATE_FAILED",
    "GENERATING",
    "GenerationProvenance",
    "INTERRUPTED",
    "LEGACY_UNVERIFIED",
    "STAGED_GENERATION_PASS",
    "STAGE_FAILED",
    "TERMINAL_STATES",
    "UnknownLifecycleStateError",
    "file_manifest",
    "hash_text",
]
