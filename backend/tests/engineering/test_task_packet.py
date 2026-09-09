"""D-036: current task packet is bounded, deterministic, and truthful.

Tested against the real repository (same convention as
`test_context_package.py`'s `ContextKindAuthority.load(REPO)`), because the
packet's whole point is to reflect real canonical state, not a fixture.
"""

from __future__ import annotations

import json
import pathlib
from typing import Final

from arkali.acceptance.governance_state import GovernanceState
from arkali.engineering.agent.task_packet import PACKET_SCHEMA, compile_task_packet

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


def test_packet_carries_its_own_schema_and_disclaims_authority() -> None:
    packet = compile_task_packet(REPO)
    assert packet["schema"] == PACKET_SCHEMA
    assert "none" in packet["authority"]


def test_packet_next_files_bounded_at_five_with_real_provenance() -> None:
    packet = compile_task_packet(REPO)
    files = packet["next_files"]
    assert 1 <= len(files) <= 5
    for entry in files:
        assert (REPO / entry["path"]).exists()
        assert entry["origin"]


def test_packet_size_stays_bootstrap_compact() -> None:
    packet = compile_task_packet(REPO)
    size = len(json.dumps(packet, ensure_ascii=False).encode("utf-8"))
    assert size < 8000


def test_packet_open_finding_matches_governance_state_truthfully() -> None:
    """Scenario H: no open HIGH/BLOCKER must be reported as none, not invented."""
    packet = compile_task_packet(REPO)
    governance = GovernanceState.load(REPO)
    stopping = governance.open_stopping_findings
    if stopping:
        assert packet["open_stopping_finding"] is not None
        assert packet["open_stopping_finding"]["id"] == sorted(stopping)[0]
    else:
        assert packet["open_stopping_finding"] is None
    assert packet["open_stopping_finding_count"] == len(stopping)


def test_packet_current_phase_matches_governance_state() -> None:
    packet = compile_task_packet(REPO)
    governance = GovernanceState.load(REPO)
    assert packet["current_phase"] == governance.current_work_phase()


def test_packet_selection_is_deterministic() -> None:
    """Scenario I: same repository state, same packet (generation time aside)."""
    first = compile_task_packet(REPO)
    second = compile_task_packet(REPO)
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_packet_head_matches_real_git_head() -> None:
    packet = compile_task_packet(REPO)
    from arkali.engineering.agent.task_packet import _git

    assert packet["head"] == _git(REPO, "rev-parse", "HEAD")
    assert packet["branch"] == _git(REPO, "rev-parse", "--abbrev-ref", "HEAD")
