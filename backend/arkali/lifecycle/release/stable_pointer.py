"""Minimal Stable-revision pointer primitive (D-017, ARK-REQ-0158).

Owner: `lifecycle.release` (Protected Core) — the matrix's own words for
Phase 22B's contract set: "an atomic stable-revision pointer — delivered
*within* Phase 22B and owned by `lifecycle.release`.  No second release
authority is created."  `lifecycle.recovery` reads this primitive through the
declared sibling edge `{from: lifecycle.recovery, to: lifecycle.release,
reason: "reads stable revision pointer"}` (`AUTHORITY_MAP.yaml`); this module
never imports `lifecycle.recovery`.

DELIBERATELY MINIMAL. This is not Phase 26's release/supply-chain/deployment
system (D-017). It answers exactly one question — "which content-addressed
revision is Stable right now, and what was Stable before it" — and nothing
else. No signing, no SBOM, no deployment.

A REVISION BECOMES ELIGIBLE ONLY THROUGH THE EXISTING CANONICAL PATH.
`promote` accepts only a `StageReceipt` that `StableCandidatePath` itself
proves traversed every canonical stage to its final `promotion` stage
(`stable_path.py`, already accepted Phase 12/13 authority). There is no
constructor here that lets a caller hand in a bare string and have it
believed: the receipt is the only proof of "previously verified" this module
accepts, so the pointer's own history *is* the record of legitimately
promoted revisions — the fact `ARK-REQ-0157` needs a rollback target to prove.

ATOMIC SWITCH, NEVER PARTIAL REWRITE (ARK-REQ-0158). The whole pointer state
— current revision plus full history — is serialised once and written to a
temp file beside the target, then `os.replace` swaps it into place in one
filesystem operation. A reader never observes a half-written pointer: it sees
either the complete previous state or the complete new one.

HISTORY IS APPEND-ONLY AND NEVER REWRITTEN. `promote` always carries the
prior current revision forward into `history`; nothing here can remove or
edit an existing entry. A tampered or truncated pointer file is refused on
read (recomputed against its own declared count), never silently repaired.

`ArkaliError` COMES FROM `error_root`, NOT `error_base`. `error_base.py`'s own
docstring asks a new consumer needing only `ArkaliError` to import
`error_root` directly rather than add to its own fan-in - found as a real,
measured `max_fan_in_per_module` violation (`error_base.py` was already at
15 of 15) by running the gate, not assumed.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import tempfile
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.kernel.contracts.content_address import is_address
from arkali.kernel.contracts.error_root import ArkaliError
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt

POINTER_VERSION: Final[str] = "1.0.0"
POINTER_FILENAME: Final[str] = "stable_pointer.json"


class StablePointerError(ArkaliError):
    """The Stable-revision pointer is malformed, tampered, or misused."""

    code = "ARK-ERR-0151"


class StableRevisionRecord(BaseModel):
    """One revision that was, or is, Stable. Immutable once written."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    revision_id: str = Field(min_length=1)
    promoted_at: dt.datetime
    candidate_id: str = Field(min_length=1)


class StablePointerState(BaseModel):
    """The whole pointer file, as one atomically-written unit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pointer_version: str = POINTER_VERSION
    current: StableRevisionRecord | None
    history: tuple[StableRevisionRecord, ...] = ()


def _validate_revision_id(revision_id: str) -> None:
    if not is_address(revision_id):
        raise StablePointerError(
            f"revision id {revision_id!r} is not a canonical content address; "
            "an identity a caller could invent is exactly what content "
            "addressing exists to refuse"
        )


class StableRevisionPointer:
    """The single Stable-revision pointer for this repository.

    Construct with the canonical `StableCandidatePath`, loaded once by the
    composition root — the same discipline every other authority in this
    build uses rather than re-parsing `AUTHORITY_MAP.yaml` per call.
    """

    def __init__(self, path: StableCandidatePath, pointer_path: pathlib.Path) -> None:
        self._path = path
        self._pointer_path = pointer_path

    @classmethod
    def open(
        cls, repo_root: pathlib.Path, state_dir: pathlib.Path
    ) -> StableRevisionPointer:
        path = StableCandidatePath.load(repo_root)
        return cls(path, state_dir / POINTER_FILENAME)

    def current(self) -> StableRevisionRecord | None:
        """The revision Stable right now, or None before any promotion."""
        return self._read().current

    def history(self) -> tuple[StableRevisionRecord, ...]:
        """Every revision that was ever Stable, oldest first. Never mutated."""
        return self._read().history

    def is_previously_verified(self, revision_id: str) -> bool:
        """Whether `revision_id` is the current Stable revision or a past one.

        This is the whole of what `ARK-REQ-0157` means by "previously
        verified immutable revision": a revision this pointer itself recorded
        through a genuine promotion receipt, never a caller's assertion.
        """
        state = self._read()
        recorded = {rec.revision_id for rec in state.history}
        if state.current is not None:
            recorded.add(state.current.revision_id)
        return revision_id in recorded

    def promote(
        self, receipt: StageReceipt, *, revision_id: str, candidate_id: str
    ) -> StableRevisionRecord:
        """Promote `revision_id` to Stable. The receipt is the only proof.

        `receipt` must be exactly the promotion-stage receipt
        `StableCandidatePath.promotion_receipt` issues for `candidate_id` —
        proof the full canonical stable-candidate path was traversed. A
        receipt for a different candidate, or one that stops short of the
        final stage, is refused before anything is written.
        """
        _validate_revision_id(revision_id)
        if receipt.candidate_id != candidate_id:
            raise StablePointerError(
                "promotion receipt does not belong to this candidate: "
                f"receipt names {receipt.candidate_id!r}, promotion requests "
                f"{candidate_id!r}"
            )
        final_stage = self._path.stages()[-1]
        if receipt.stage != final_stage or receipt.traversed != self._path.stages():
            raise StablePointerError(
                "promotion requires a receipt that traversed the complete "
                f"canonical path to {final_stage!r}; refusing a partial or "
                "wrong-stage receipt"
            )

        state = self._read()
        new_history = state.history
        if state.current is not None:
            new_history = (*new_history, state.current)
        record = StableRevisionRecord(
            revision_id=revision_id,
            promoted_at=dt.datetime.now(dt.UTC),
            candidate_id=candidate_id,
        )
        self._write(
            StablePointerState(current=record, history=new_history)
        )
        return record

    def rollback_to(self, revision_id: str) -> StableRevisionRecord:
        """Atomically switch Stable back to a previously verified revision.

        The raw mechanic only. It carries no policy decision and does not
        consult the policy authority - the sole legitimate caller
        (`lifecycle.recovery`'s Recovery Supervisor, Phase 22B) always obtains
        its own real, unattended grant from that authority first and calls
        this only after that grant is in hand, the same order
        `migration_safety.py`'s Apply step already uses against its own
        approval gate. Refuses any target this pointer never itself recorded
        (`ARK-REQ-0157`) - the abandoned current revision is carried into
        history, never discarded, so this operation is never lossy.
        """
        _validate_revision_id(revision_id)
        state = self._read()
        if not self.is_previously_verified(revision_id):
            raise StablePointerError(
                f"rollback target {revision_id!r} was never recorded as Stable "
                "by this pointer; refusing to roll back to an unverified or "
                "unknown revision"
            )
        if state.current is not None and state.current.revision_id == revision_id:
            return state.current
        target = next(
            (rec for rec in state.history if rec.revision_id == revision_id), None
        )
        if target is None:
            raise StablePointerError(
                f"rollback target {revision_id!r} could not be resolved to a "
                "recorded revision"
            )
        # The target leaves history to become current; the abandoned current
        # joins history in its place, preserving the remaining chronology.
        new_history = tuple(rec for rec in state.history if rec.revision_id != revision_id)
        if state.current is not None:
            new_history = (*new_history, state.current)
        self._write(StablePointerState(current=target, history=new_history))
        return target

    def _read(self) -> StablePointerState:
        if not self._pointer_path.is_file():
            return StablePointerState(current=None, history=())
        try:
            raw = json.loads(self._pointer_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StablePointerError(
                f"pointer file at {self._pointer_path.name} is not readable JSON"
            ) from exc
        try:
            state = StablePointerState(**raw)
        except Exception as exc:  # pydantic validation, reported not repaired
            raise StablePointerError(
                f"pointer file does not satisfy its contract: {exc}"
            ) from exc
        if state.pointer_version.split(".")[0] != POINTER_VERSION.split(".")[0]:
            raise StablePointerError(
                f"pointer major version {state.pointer_version} is not readable "
                f"by this implementation ({POINTER_VERSION})"
            )
        return state

    def _write(self, state: StablePointerState) -> None:
        """Serialise the whole state once, then swap it in atomically."""
        self._pointer_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            json.loads(state.model_dump_json()), indent=2, sort_keys=True
        )
        fd, tmp_name = tempfile.mkstemp(
            dir=self._pointer_path.parent, prefix=".stable_pointer_", suffix=".tmp"
        )
        try:
            with open(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self._pointer_path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
