from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "run_staged_generation.py"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_a_candidate_identity_is_claimed_in_the_ledger_before_any_workspace_is_allocated() -> None:
    """golden-work-124: WorkspaceAuthority.allocate only refuses a live
    directory collision; the ledger must claim the identity first, so a
    reused candidate_id is refused even before a directory is touched."""
    source = _source()
    ledger_allocate = source.index("ledger.allocate(args.candidate_id")
    workspace_allocate = source.index("WorkspaceAuthority(candidates_root).allocate(")
    assert ledger_allocate < workspace_allocate


def test_every_terminal_outcome_records_the_candidate_ledger() -> None:
    source = _source()
    for outcome_marker in ("STAGE_FAILED", "FINAL_GATE_FAILED", "STAGED_GENERATION_PASS"):
        assert outcome_marker in source
    assert source.count("ledger.record_state(") >= 4  # GENERATING + the 3 terminal branches


def test_an_unexpected_interruption_records_interrupted_before_re_raising() -> None:
    source = _source()
    handler = source.index("except (KeyboardInterrupt, Exception):")
    record_interrupted = source.index("INTERRUPTED, workspace.root")
    reraise = source.index("raise", handler)
    assert handler < record_interrupted < reraise


def test_provenance_captures_goal_hash_source_commit_model_and_runtime() -> None:
    source = _source()
    provenance_call = source[source.index("GenerationProvenance(") : source.index("ledger.allocate(")]
    for field in ("goal_hash=", "source_commit=", "runtime=args.runtime", "model=args.model"):
        assert field in provenance_call
