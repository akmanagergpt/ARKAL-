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


def test_the_campaign_budget_gate_runs_before_any_candidate_identity_or_workspace_is_claimed() -> None:
    """"Bütçe aşımında kullanıcı onayı olmadan yeni aday başlamasın" -- a
    live call into `main()` cannot safely be unit-tested without either
    mutating the real `var/factory/` state or mocking away everything the
    ordering itself is meant to protect, so this asserts the one property
    that actually matters mechanically: the campaign gate is checked
    strictly before the candidate_id is claimed in the ledger, which in
    turn happens strictly before a workspace directory is allocated. The
    underlying refusal logic itself is unit-tested directly in
    test_campaign_budget.py and test_candidate_ledger.py."""
    source = _source()
    budget_gate = source.index("campaign.refuse_new_candidate_unless_permitted")
    ledger_allocate = source.index("ledger.allocate(args.candidate_id")
    workspace_allocate = source.index("WorkspaceAuthority(candidates_root).allocate(")
    assert budget_gate < ledger_allocate < workspace_allocate


def test_every_terminal_outcome_records_both_the_candidate_ledger_and_the_campaign_ledger() -> None:
    source = _source()
    for outcome_marker in ("STAGE_FAILED", "FINAL_GATE_FAILED", "STAGED_GENERATION_PASS"):
        assert outcome_marker in source
    assert source.count("ledger.record_state(") >= 4  # GENERATING + the 3 terminal branches
    assert source.count("campaign.record(") >= 3


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


def test_the_accepted_goal_check_runs_before_any_candidate_identity_or_model_invocation() -> None:
    """Human governance decision (session record): a normal new generation
    campaign for an already-ACCEPTED goal must be refused before the
    candidate identity is claimed and before any model/provider is
    invoked. Same reasoning as the campaign-budget ordering test above --
    `main()` cannot safely be unit-tested end to end without mutating real
    `var/factory/` state or a real Ollama call, so this asserts the one
    property that mechanically matters: strict source order. The
    underlying refusal logic itself is unit-tested directly in
    test_candidate_ledger.py::TestAcceptedGoalTermination."""
    source = _source()
    accepted_goal_check = source.index("ledger.accepted_candidate_for_goal(goal_hash)")
    budget_gate = source.index("campaign.refuse_new_candidate_unless_permitted")
    ledger_allocate = source.index("ledger.allocate(args.candidate_id")
    workspace_allocate = source.index("WorkspaceAuthority(candidates_root).allocate(")
    model_invocation = source.index("generate_staged_model_product(")
    assert (
        accepted_goal_check < budget_gate < ledger_allocate
        < workspace_allocate < model_invocation
    )


def test_the_accepted_goal_check_raises_before_deriving_a_blueprint() -> None:
    """The refusal must happen before any further work on the goal begins
    at all -- not merely before the candidate/model steps."""
    source = _source()
    accepted_goal_check = source.index("raise GoalAlreadyAcceptedError")
    blueprint_derivation = source.index("derive_blueprint(goal_text")
    assert accepted_goal_check < blueprint_derivation
