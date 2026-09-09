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
