"""D-036 current task packet: compact, deterministic session-bootstrap navigation.

Lives in `scripts/`, not `backend/arkali/`, on purpose. An earlier version of
this compiler lived at `backend/arkali/engineering/agent/task_packet.py` and
imported `arkali.acceptance.governance_state`/`arkali.acceptance.findings`
from there; the live architecture gate (`scripts/handoff_architecture.py`)
immediately measured a real new cross-context edge and pushed orchestration
depth to 5 of a 4 ceiling (`engineering.agent -> acceptance.engine ->
control.specification -> control.architecture -> kernel.contracts`), which
`check_handoff.py` correctly reported as `HANDOFF_DRIFT`. `scripts/` is
deliberately not part of that package graph - `handoff_architecture.py`,
`handoff_findings.py` and `check_handoff.py` already reach across
`arkali.acceptance`/`arkali.control.architecture`/etc. from here for exactly
this reason (see `backend/tests/governance/handoff_harness.py`'s own
docstring: "`scripts/` is not a package and never becomes one"). Moving the
compiler here removes the edge instead of budgeting around it.

NOT A SECOND TRUTH STORE. This module derives a small navigation packet from
already-canonical sources (`docs/build/OPEN_BLOCKERS.md`,
`docs/build/BUILD_STATE.md`, `ARKALI_HANDOFF.md`, git). It stores no state of
its own, invents no requirement, and closes no finding. If the packet is stale
or conflicts with those sources, the sources win.

DETERMINISTIC AND MODEL-FREE. No provider call, no LLM summarisation. Every
field is either read straight from a canonical document via an existing
parser (`arkali.acceptance.findings`, `arkali.acceptance.governance_state`) or
computed by a fixed rule (the HEAD-marked handoff row, git porcelain status).

REUSES C-23 FOR THE NEXT-FILES LIST. `ContextPackage.compiled` is the existing
constructor for "a bounded list of things to look at, each with real
provenance". C-22 `HarnessTask` is deliberately NOT used: its required
`tools`/`permissions`/`acceptance_target`/`repair_budget` fields presuppose an
actual bounded task, and a pure navigation packet - especially the current,
real state where no finding is open - has none of those to declare honestly.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from arkali.acceptance.findings import Finding, parse_findings  # noqa: E402
from arkali.acceptance.governance_state import (  # noqa: E402
    OPEN_BLOCKERS,
    GovernanceState,
)
from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.engineering.agent.context_kinds import ContextKindAuthority  # noqa: E402
from arkali.engineering.agent.context_package import (  # noqa: E402
    ContextItem,
    ContextPackage,
)
from arkali.execution.durable.job_state_machine import (  # noqa: E402
    CHECKPOINTED,
    PAUSED,
    QUEUED,
    RECOVERABLE,
    RESUMING,
    RUNNING,
)
from arkali.execution.durable.job_store import JobStore  # noqa: E402
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
    sqlite_url,
)
from arkali.kernel.persistence.session import (  # noqa: E402
    create_session_factory,
    unit_of_work,
)

PACKET_SCHEMA = "arkali.task_packet/1"
HANDOFF = "ARKALI_HANDOFF.md"
BUILD_STATE = "docs/build/BUILD_STATE.md"
COMMAND_CENTER_DB = "var/command_center.db"

#: Every non-terminal `Job` machine state (`STATE_MACHINES.md` §3) - a job in
#: any of these is real, live, unfinished operational work.
_ACTIVE_JOB_STATES: tuple[str, ...] = (
    QUEUED, RUNNING, CHECKPOINTED, PAUSED, RESUMING, RECOVERABLE,
)

#: The one job type this task packet checks live, since it is the one D-036's
#: own `next_exact_action` text has already been observed pointing at
#: (`scripts/run_product_change_worker.py`'s "ready_for_review" checkpoint
#: phase). Not a general-purpose registry: a second domain needing the same
#: live check gets its own named constant here, never a guess over all types.
_PRODUCT_CHANGE_JOB_TYPE = "managed_product.change"
_READY_FOR_REVIEW_PHASE = "ready_for_review"

#: A narrow, explicit vocabulary for recognising when the free-text
#: `next_exact_action` (sourced from `ARKALI_HANDOFF.md`, unchanged, still the
#: sole authority) is making a claim about THIS ONE checked operational
#: domain - a pending product-change review. This is not a staleness oracle
#: over arbitrary prose; it flags exactly one thing: "this text talks about a
#: product-change proposal, and live JobStore currently shows none pending",
#: so a reading session sees the conflict instead of re-deriving it by hand.
_PRODUCT_CHANGE_TEXT_MARKERS: tuple[str, ...] = (
    "accept/reject", "ready_for_review", "ready for review",
    "restore-as-new", "restore proof",
)

#: A commit-ledger row this document itself marks as matching current HEAD.
#: Reused rather than "the last numbered row": `check_handoff.py` already
#: treats this exact marker as the ledger's freshness signal, so a second
#: convention here would be a second, competing definition of "live". Rows are
#: single lines, so DOTALL is deliberately not used - it would let the
#: non-greedy body swallow earlier rows when only one marker exists.
_HEAD_ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*`(?P<commit>[0-9a-f]+)`\s*\|(?P<body>.*?)"
    r"←\s*HEAD at generation\s*\|",
    re.M,
)
_NEXT_ACTION = re.compile(
    r"\*\*NEXT EXACT ACTION:\s*(?P<action>.*?)\*\*", re.S,
)


def _git(repo_root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _read(repo_root: pathlib.Path, relpath: str) -> str:
    path = repo_root / relpath
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _latest_head_row(handoff_text: str) -> tuple[str, str] | None:
    last = None
    for last in _HEAD_ROW.finditer(handoff_text):
        pass
    return (last.group("commit"), last.group("body")) if last else None


def _next_exact_action(row_body: str) -> str | None:
    found = _NEXT_ACTION.search(row_body)
    return " ".join(found.group("action").split()) if found else None


def _next_files(repo_root: pathlib.Path) -> tuple[ContextItem, ...]:
    """Bounded, deterministic navigation - never a dependency crawl.

    Fixed candidates only, each verified to exist before being offered. Per
    D-036 section 6, an owner that cannot be derived this safely is left out
    rather than guessed - `compile_task_packet` records that gap in
    `further_lookup_required` instead of inventing a file.
    """
    candidates = (
        (OPEN_BLOCKERS, "canonical open-findings ledger"),
        (HANDOFF, "latest HEAD-marked commit row / live next action"),
        (BUILD_STATE, "canonical phase and gate status"),
        (
            "backend/arkali/engineering/product_change/promotion.py",
            "implementation owner: accept/reject path named by the live next action",
        ),
        (
            "backend/arkali/engineering/product_change/restore.py",
            "implementation owner: restore path named by the live next action",
        ),
    )
    items = []
    for path, origin in candidates:
        if (repo_root / path).is_file():
            items.append(ContextItem(kind="files", identifier=path, origin=origin))
    return tuple(items[:5])


def _operational_snapshot(repo_root: pathlib.Path) -> dict[str, Any]:
    """The minimum live ProjectRegistry/JobStore read needed to keep
    `next_exact_action` from silently going stale once the one operational
    proposal it names resolves - `var/command_center.db`'s own live
    `durable_job`/`job_checkpoint` rows, read through the existing
    `JobStore`, never a raw query.

    NOT A SECOND TRUTH STORE (per this task's own rule 3): this never edits
    or replaces `next_exact_action`'s text, which stays sourced from
    `ARKALI_HANDOFF.md` alone. It only reports what is live-true right now,
    so `next_exact_action_potentially_stale` below can say "these two
    disagree" without this compiler ever deciding which one is right -
    identical in spirit to `CANONICAL_AMBIGUITY`: disclose, never guess.

    Best-effort and read-only: an absent database (a fresh checkout that has
    never run Command Center) or any read failure degrades to
    `{"available": False}` rather than raising, matching
    `arkali_memory.py::_task_packet_payload`'s own None-on-failure contract
    for this same packet.
    """
    db_path = repo_root / COMMAND_CENTER_DB
    if not db_path.is_file():
        return {"available": False}

    try:
        engine = create_persistence_engine(sqlite_url(db_path))
        factory = create_session_factory(engine)
        pdp = PolicyDecisionPoint.load(repo_root)
        with unit_of_work(factory) as session:
            pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
            store = JobStore(session, pep)
            active = store.list_by_state(_ACTIVE_JOB_STATES)

            ready_for_review: list[dict[str, str]] = []
            for job in active:
                if job.job_type != _PRODUCT_CHANGE_JOB_TYPE:
                    continue
                checkpoints = store.checkpoints(job.job_id)
                phase = checkpoints[-1].payload.get("phase") if checkpoints else None
                if phase == _READY_FOR_REVIEW_PHASE:
                    ready_for_review.append({
                        "job_id": job.job_id,
                        "project_id": str(job.payload.get("project_id", "")),
                    })

            return {
                "available": True,
                "active_job_count": len(active),
                "ready_for_review": ready_for_review,
            }
    except Exception:
        return {"available": False}


def _live_next_action_hint(
    stopping_count: int, snapshot: dict[str, Any],
) -> str:
    """One of the states rule 4 asks this packet to distinguish.

    Order matters and matches priority, not chronology: an open
    HIGH/BLOCKER always outranks live operational state (repository
    governance truth stays canonical per rule 3), live review-ready work
    outranks a merely-running job, and "unavailable" is honestly reported
    rather than defaulting to "nothing pending".
    """
    if stopping_count > 0:
        return "resolve_open_finding"
    if not snapshot["available"]:
        return "live_state_unavailable"
    if snapshot["ready_for_review"]:
        return "review_pending_product_change"
    if snapshot["active_job_count"] > 0:
        return "pending_operational_job"
    return "no_pending_operational_work"


def _next_action_potentially_stale(next_action: str | None, hint: str) -> bool:
    """Narrow conflict check, scoped only to `_PRODUCT_CHANGE_TEXT_MARKERS`.

    True only when the static text itself claims a pending product-change
    review AND live JobStore currently shows none. Never fires for any other
    kind of `next_exact_action` text - a second domain needs its own marker
    list and its own reasoning here, not a broadened guess.
    """
    if next_action is None or hint != "no_pending_operational_work":
        return False
    lowered = next_action.lower()
    return any(marker in lowered for marker in _PRODUCT_CHANGE_TEXT_MARKERS)


def compile_task_packet(repo_root: pathlib.Path) -> dict[str, Any]:
    """Derive the current task packet. Read-only: writes nothing itself."""
    branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(repo_root, "rev-parse", "HEAD")
    dirty = bool(_git(repo_root, "status", "--porcelain"))

    governance = GovernanceState.load(repo_root)
    phase = governance.current_work_phase()
    stopping = governance.open_stopping_findings

    all_findings: tuple[Finding, ...] = parse_findings(_read(repo_root, OPEN_BLOCKERS))
    top_finding: dict[str, str] | None = None
    if stopping:
        by_id = {finding.identifier: finding for finding in all_findings}
        candidate = by_id.get(sorted(stopping)[0])
        if candidate is not None:
            top_finding = {
                "id": candidate.identifier,
                "severity": candidate.severity,
                "status": candidate.status.name,
                "detail": " ".join(candidate.detail.split())[:200],
            }

    head_row = _latest_head_row(_read(repo_root, HANDOFF))
    next_action = _next_exact_action(head_row[1]) if head_row else None

    live = _operational_snapshot(repo_root)
    live_hint = _live_next_action_hint(len(stopping), live)

    authority = ContextKindAuthority.load(repo_root)
    files = _next_files(repo_root)
    package = ContextPackage.compiled(
        authority,
        package_id="d036-task-packet-next-files",
        task_id=f"task-packet-{head[:12]}",
        items=files,
    )

    return {
        "schema": PACKET_SCHEMA,
        "authority": "none; derived navigation only, source and canonical documents win",
        "generated_at": datetime.now(UTC).isoformat(),
        "branch": branch,
        "head": head,
        "working_tree_clean": not dirty,
        "current_phase": phase,
        "open_stopping_finding_count": len(stopping),
        "open_stopping_finding": top_finding,
        "next_exact_action": next_action,
        "next_exact_action_potentially_stale": _next_action_potentially_stale(
            next_action, live_hint,
        ),
        "live_operational_state": {**live, "hint": live_hint},
        "next_files": [
            {"path": item.identifier, "origin": item.origin} for item in package.items
        ],
        "further_lookup_required": len(files) < 5,
        "sources": [OPEN_BLOCKERS, HANDOFF, BUILD_STATE],
        "context_hash": package.context_hash,
    }


def main() -> int:
    import json

    print(json.dumps(compile_task_packet(REPO), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
