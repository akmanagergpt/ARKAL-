"""D-036: current task packet is bounded, deterministic, and truthful.

Loaded by path, like `handoff_harness.py` loads `check_handoff.py`/
`handoff_architecture.py`: `scripts/` is deliberately not a package, and is
outside the `backend/arkali` context-edge budget the live architecture gate
measures - the reason this compiler lives there at all (see
`scripts/task_packet.py`'s own docstring for the drift it was moved to avoid).
"""

from __future__ import annotations

import json
import pathlib
from typing import Final

from arkali.acceptance.governance_state import GovernanceState
from tests.governance.handoff_harness import load_architecture, load_module

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
TASK_PACKET = REPO / "scripts" / "task_packet.py"


def _module():
    return load_module(TASK_PACKET)


def test_packet_carries_its_own_schema_and_disclaims_authority() -> None:
    tp = _module()
    packet = tp.compile_task_packet(REPO)
    assert packet["schema"] == tp.PACKET_SCHEMA
    assert "none" in packet["authority"]


def test_packet_next_files_bounded_at_five_with_real_provenance() -> None:
    packet = _module().compile_task_packet(REPO)
    files = packet["next_files"]
    assert 1 <= len(files) <= 5
    for entry in files:
        assert (REPO / entry["path"]).exists()
        assert entry["origin"]


def test_packet_size_stays_bootstrap_compact() -> None:
    packet = _module().compile_task_packet(REPO)
    size = len(json.dumps(packet, ensure_ascii=False).encode("utf-8"))
    assert size < 8000


def test_packet_open_finding_matches_governance_state_truthfully() -> None:
    """Scenario H: no open HIGH/BLOCKER must be reported as none, not invented."""
    packet = _module().compile_task_packet(REPO)
    governance = GovernanceState.load(REPO)
    stopping = governance.open_stopping_findings
    if stopping:
        assert packet["open_stopping_finding"] is not None
        assert packet["open_stopping_finding"]["id"] == sorted(stopping)[0]
    else:
        assert packet["open_stopping_finding"] is None
    assert packet["open_stopping_finding_count"] == len(stopping)


def test_packet_current_phase_matches_governance_state() -> None:
    packet = _module().compile_task_packet(REPO)
    governance = GovernanceState.load(REPO)
    assert packet["current_phase"] == governance.current_work_phase()


def test_packet_selection_is_deterministic() -> None:
    """Scenario I: same repository state, same packet (generation time aside)."""
    tp = _module()
    first = tp.compile_task_packet(REPO)
    second = tp.compile_task_packet(REPO)
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_packet_head_matches_real_git_head() -> None:
    tp = _module()
    packet = tp.compile_task_packet(REPO)
    assert packet["head"] == tp._git(REPO, "rev-parse", "HEAD")
    assert packet["branch"] == tp._git(REPO, "rev-parse", "--abbrev-ref", "HEAD")


def test_packet_does_not_regress_the_live_architecture_gate() -> None:
    """The exact regression this compiler was moved out of `backend/arkali/` to avoid."""
    architecture = load_architecture()
    truth = architecture.architecture_truth(REPO)
    assert truth["violations"] == 0
    assert truth["depth"] <= truth["depth_allowed"]


# -- live-state correction (task-packet live-state fix) ----------------------


def test_packet_carries_live_operational_state_and_hint() -> None:
    """Every packet now reports the live JobStore snapshot it read, never
    only a static doc claim about operational work."""
    packet = _module().compile_task_packet(REPO)
    live = packet["live_operational_state"]
    assert "available" in live and "hint" in live
    assert live["hint"] in {
        "resolve_open_finding", "live_state_unavailable",
        "review_pending_product_change", "pending_operational_job",
        "no_pending_operational_work",
    }
    assert isinstance(packet["next_exact_action_potentially_stale"], bool)


def test_open_finding_always_outranks_live_operational_state() -> None:
    """Repository/governance truth stays canonical (rule 3): an open
    HIGH/BLOCKER wins the hint regardless of what JobStore shows."""
    tp = _module()
    hint = tp._live_next_action_hint(
        1, {"available": True, "active_job_count": 3, "ready_for_review": [{"job_id": "x"}]},
    )
    assert hint == "resolve_open_finding"


def test_ready_for_review_is_recognised_live() -> None:
    """Scenario: an active READY_FOR_REVIEW product-change proposal exists."""
    tp = _module()
    hint = tp._live_next_action_hint(
        0, {"available": True, "active_job_count": 1, "ready_for_review": [{"job_id": "x"}]},
    )
    assert hint == "review_pending_product_change"


def test_pending_job_without_review_is_distinguished_from_idle() -> None:
    tp = _module()
    hint = tp._live_next_action_hint(
        0, {"available": True, "active_job_count": 1, "ready_for_review": []},
    )
    assert hint == "pending_operational_job"


def test_no_open_finding_and_no_pending_work_yields_truthful_idle_hint() -> None:
    """Scenario: a completed/live-proven cycle must not suggest replay."""
    tp = _module()
    hint = tp._live_next_action_hint(
        0, {"available": True, "active_job_count": 0, "ready_for_review": []},
    )
    assert hint == "no_pending_operational_work"


def test_unavailable_live_state_is_reported_not_assumed_idle() -> None:
    tp = _module()
    hint = tp._live_next_action_hint(0, {"available": False})
    assert hint == "live_state_unavailable"


def test_stale_static_next_action_flagged_only_against_its_own_marker() -> None:
    """The exact real conflict this fix targets: static text still claiming
    a pending product-change accept/reject/restore review while live
    JobStore shows nothing pending - flagged, never silently corrected."""
    tp = _module()
    stale_text = (
        "proceed with the governed P4 accept/reject/restore proof on the "
        "existing product; no new Factory generation."
    )
    assert tp._next_action_potentially_stale(
        stale_text, "no_pending_operational_work",
    ) is True
    # Same idle hint, unrelated text: never flagged - the check is scoped to
    # its own narrow marker vocabulary, not a general staleness guess.
    assert tp._next_action_potentially_stale(
        "run the full backend regression suite.", "no_pending_operational_work",
    ) is False
    # Matching text, but live state shows real pending work: not stale.
    assert tp._next_action_potentially_stale(
        stale_text, "review_pending_product_change",
    ) is False
    assert tp._next_action_potentially_stale(None, "no_pending_operational_work") is False


def test_operational_snapshot_degrades_safely_without_a_live_database(
    tmp_path: pathlib.Path,
) -> None:
    """A fresh checkout with no `var/command_center.db` yet must degrade to
    `available: False`, never raise and never claim work is pending."""
    tp = _module()
    snapshot = tp._operational_snapshot(tmp_path)
    assert snapshot == {"available": False}


def test_operational_snapshot_reflects_the_real_repository_database() -> None:
    """Live-proven against this repository's own real `var/command_center.db`
    (not a fixture): the snapshot must be internally consistent, whatever the
    live state currently is."""
    tp = _module()
    snapshot = tp._operational_snapshot(REPO)
    if snapshot["available"]:
        assert snapshot["active_job_count"] >= len(snapshot["ready_for_review"])
        for entry in snapshot["ready_for_review"]:
            assert entry["job_id"]
