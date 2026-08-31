from __future__ import annotations

import pathlib

import pytest

from arkali.engineering.candidate.errors import (
    CandidateIdentityReuseError,
    CandidateIntegrityError,
)
from arkali.engineering.candidate.ledger import (
    ACCEPTANCE_RUNNING,
    ACCEPTED,
    ALLOCATED,
    CandidateLedger,
    GenerationProvenance,
    GENERATING,
    file_manifest,
    hash_text,
    INTERRUPTED,
    LEGACY_UNVERIFIED,
    STAGED_GENERATION_PASS,
    STAGE_FAILED,
)


def _provenance(**overrides: object) -> GenerationProvenance:
    values: dict[str, object] = {
        "goal_hash": hash_text("goal A"),
        "source_commit": "abc123",
        "runtime": "ollama",
        "endpoint": "http://localhost:11434",
        "model": "qwen2.5-coder:14b",
        "model_parameters": {"max_output_tokens": 4096},
        "pipeline_version": "phase-30-staged-generation/1.0.0",
    }
    values.update(overrides)
    return GenerationProvenance(**values)  # type: ignore[arg-type]


def _write(root: pathlib.Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestIdentityReuse:
    def test_the_same_candidate_id_cannot_be_allocated_twice(self, tmp_path: pathlib.Path) -> None:
        """golden-work-124 (real repository evidence): WorkspaceAuthority.allocate
        only refuses a live directory collision; the ledger must refuse the
        identity itself, independent of the filesystem."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        ledger.allocate("golden-work-999", provenance=_provenance())
        with pytest.raises(CandidateIdentityReuseError):
            ledger.allocate("golden-work-999", provenance=_provenance())

    def test_a_deleted_workspace_directory_does_not_free_its_candidate_id(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """The exact golden-work-124 concern: delete the directory and the
        identity must still refuse reuse, since the ledger -- not the
        filesystem -- is the authority on "has this id ever existed"."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-999"
        work.mkdir(parents=True)
        _write(work, "a.txt", "hello")
        ledger.allocate("golden-work-999", provenance=_provenance())
        ledger.record_state("golden-work-999", GENERATING, work)
        ledger.record_state("golden-work-999", STAGED_GENERATION_PASS, work)

        import shutil
        shutil.rmtree(work)
        assert not work.exists()

        with pytest.raises(CandidateIdentityReuseError):
            ledger.allocate("golden-work-999", provenance=_provenance())


class TestIntegrityVerification:
    def test_an_unmodified_candidate_verifies_cleanly(self, tmp_path: pathlib.Path) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-1"
        work.mkdir(parents=True)
        _write(work, "a.txt", "hello")
        ledger.allocate("golden-work-1", provenance=_provenance())
        ledger.record_state("golden-work-1", GENERATING, work)
        ledger.record_state("golden-work-1", STAGED_GENERATION_PASS, work)
        ledger.verify_integrity("golden-work-1", work)  # must not raise

    def test_a_changed_file_after_the_terminal_state_is_rejected(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-2"
        work.mkdir(parents=True)
        _write(work, "a.txt", "hello")
        ledger.allocate("golden-work-2", provenance=_provenance())
        ledger.record_state("golden-work-2", GENERATING, work)
        ledger.record_state("golden-work-2", STAGED_GENERATION_PASS, work)

        _write(work, "a.txt", "tampered")
        with pytest.raises(CandidateIntegrityError, match=r"changed=\['a\.txt'\]"):
            ledger.verify_integrity("golden-work-2", work)

    def test_an_added_file_after_the_terminal_state_is_rejected(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-3"
        work.mkdir(parents=True)
        _write(work, "a.txt", "hello")
        ledger.allocate("golden-work-3", provenance=_provenance())
        ledger.record_state("golden-work-3", GENERATING, work)
        ledger.record_state("golden-work-3", STAGED_GENERATION_PASS, work)

        _write(work, "planted.txt", "not part of the original candidate")
        with pytest.raises(CandidateIntegrityError, match=r"added=\['planted\.txt'\]"):
            ledger.verify_integrity("golden-work-3", work)

    def test_a_removed_file_after_the_terminal_state_is_rejected(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-4"
        work.mkdir(parents=True)
        _write(work, "a.txt", "hello")
        _write(work, "b.txt", "world")
        ledger.allocate("golden-work-4", provenance=_provenance())
        ledger.record_state("golden-work-4", GENERATING, work)
        ledger.record_state("golden-work-4", STAGED_GENERATION_PASS, work)

        (work / "b.txt").unlink()
        with pytest.raises(CandidateIntegrityError, match=r"removed=\['b\.txt'\]"):
            ledger.verify_integrity("golden-work-4", work)

    def test_verify_integrity_does_not_modify_the_candidate_directory(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """Acceptance must observe the source candidate, never mutate it --
        recomputing a manifest is read-only."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-5"
        work.mkdir(parents=True)
        _write(work, "a.txt", "hello")
        ledger.allocate("golden-work-5", provenance=_provenance())
        ledger.record_state("golden-work-5", GENERATING, work)
        ledger.record_state("golden-work-5", STAGED_GENERATION_PASS, work)

        before = file_manifest(work)
        ledger.verify_integrity("golden-work-5", work)
        after = file_manifest(work)
        assert before == after

    def test_a_never_allocated_legacy_candidate_cannot_be_verified(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """A pre-existing candidate directory this ledger has no history for
        must never be treated as verified -- acceptance refuses it too,
        since "unchanged since when" has no answer without a baseline."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-legacy"
        work.mkdir(parents=True)
        _write(work, "a.txt", "hello")

        assert ledger.classify("golden-work-legacy") == LEGACY_UNVERIFIED
        with pytest.raises(CandidateIntegrityError):
            ledger.verify_integrity("golden-work-legacy", work)

    def test_a_non_terminal_candidate_cannot_be_verified(self, tmp_path: pathlib.Path) -> None:
        """A candidate still mid-generation (its latest recorded state is
        ALLOCATED or GENERATING, not a terminal state) has no terminal
        manifest yet and must not be accepted as though it were complete."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-6"
        work.mkdir(parents=True)
        _write(work, "a.txt", "hello")
        ledger.allocate("golden-work-6", provenance=_provenance())
        ledger.record_state("golden-work-6", GENERATING, work)

        with pytest.raises(CandidateIntegrityError):
            ledger.verify_integrity("golden-work-6", work)


class TestLifecycleClassification:
    def test_a_stage_failure_is_not_a_staged_generation_pass(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """A partial candidate whose stage failed must never be
        classified as though staged generation had passed."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-124"
        work.mkdir(parents=True)
        _write(work, "frontend/src/App.js", "// only frontend_ui's output")
        ledger.allocate("golden-work-124", provenance=_provenance())
        ledger.record_state("golden-work-124", GENERATING, work)
        ledger.record_state(
            "golden-work-124", STAGE_FAILED, work,
            detail={"error": "stage 'frontend_forms' exhausted 4 attempts"},
        )
        assert ledger.classify("golden-work-124") == STAGE_FAILED
        assert ledger.classify("golden-work-124") != STAGED_GENERATION_PASS

    def test_an_interrupted_run_is_recorded_as_its_own_terminal_state(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-7"
        work.mkdir(parents=True)
        ledger.allocate("golden-work-7", provenance=_provenance())
        ledger.record_state("golden-work-7", GENERATING, work)
        ledger.record_state("golden-work-7", INTERRUPTED, work)
        assert ledger.classify("golden-work-7") == INTERRUPTED

    def test_recording_requires_a_terminal_or_recognized_state(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-8"
        work.mkdir(parents=True)
        ledger.allocate("golden-work-8", provenance=_provenance())
        with pytest.raises(Exception):
            ledger.record_state("golden-work-8", "NOT_A_REAL_STATE", work)

    def test_recording_refuses_an_identity_never_allocated(self, tmp_path: pathlib.Path) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-9"
        work.mkdir(parents=True)
        with pytest.raises(CandidateIdentityReuseError):
            ledger.record_state("golden-work-9", STAGED_GENERATION_PASS, work)


class TestProvenanceCapture:
    def test_a_different_goal_hash_is_visible_in_the_recorded_provenance(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        ledger.allocate("golden-work-a", provenance=_provenance(goal_hash=hash_text("goal A")))
        ledger.allocate("golden-work-b", provenance=_provenance(goal_hash=hash_text("goal B")))

        a = ledger.history("golden-work-a")[0]
        b = ledger.history("golden-work-b")[0]
        assert a["state"] == ALLOCATED
        assert a["goal_hash"] != b["goal_hash"]
        assert a["goal_hash"] == hash_text("goal A")

    def test_a_different_model_or_runtime_is_visible_in_the_recorded_provenance(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        ledger.allocate(
            "golden-work-c",
            provenance=_provenance(model="qwen2.5-coder:14b", runtime="ollama"),
        )
        ledger.allocate(
            "golden-work-d",
            provenance=_provenance(model="llama3.1:8b", runtime="openai-compatible"),
        )

        c = ledger.history("golden-work-c")[0]
        d = ledger.history("golden-work-d")[0]
        assert (c["model"], c["runtime"]) != (d["model"], d["runtime"])


def _accept(ledger: CandidateLedger, candidate_id: str, work: pathlib.Path, *, goal_hash: str) -> None:
    """Drives a real candidate through every real transition to `ACCEPTED`
    (`ALLOCATED -> GENERATING -> STAGED_GENERATION_PASS -> ACCEPTANCE_RUNNING
    -> ACCEPTED`) using the ledger's own real `record_state`, exactly the
    sequence `run_staged_generation.py` and `run_golden_acceptance.py`
    together produce for a real ACCEPTED candidate -- never a shortcut
    state."""
    work.mkdir(parents=True, exist_ok=True)
    ledger.allocate(candidate_id, provenance=_provenance(goal_hash=goal_hash))
    ledger.record_state(candidate_id, GENERATING, work)
    ledger.record_state(candidate_id, STAGED_GENERATION_PASS, work)
    ledger.record_state(candidate_id, ACCEPTANCE_RUNNING, work)
    ledger.record_state(candidate_id, ACCEPTED, work)


class TestAcceptedGoalTermination:
    """Human governance decision (session record): once a real candidate
    for a goal reaches ACCEPTED, a normal new generation campaign for the
    identical goal identity must be refused. `accepted_candidate_for_goal`
    is the one, existing-ledger-backed mechanism `run_staged_generation.py`
    consults for this -- no second goal registry, no new ledger."""

    def test_a_fresh_goal_with_no_prior_candidate_is_not_blocked(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """Case A: same goal, no prior candidate at all -- generation allowed."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        assert ledger.accepted_candidate_for_goal(hash_text("goal never attempted")) is None

    def test_a_goal_whose_only_candidates_failed_or_were_interrupted_is_not_blocked(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """Case B: same goal, prior candidates exist but none reached
        ACCEPTED -- generation remains allowed (these are legitimately
        re-generatable, per campaign_budget.py's own separate budget/
        anti-loop concern, not this invariant's)."""
        goal_hash = hash_text("goal with only failures")
        ledger = CandidateLedger(tmp_path / "_ledger")
        failed_work = tmp_path / "candidates" / "golden-work-fail"
        failed_work.mkdir(parents=True)
        ledger.allocate("golden-work-fail", provenance=_provenance(goal_hash=goal_hash))
        ledger.record_state("golden-work-fail", GENERATING, failed_work)
        ledger.record_state("golden-work-fail", STAGE_FAILED, failed_work)

        interrupted_work = tmp_path / "candidates" / "golden-work-interrupted"
        interrupted_work.mkdir(parents=True)
        ledger.allocate("golden-work-interrupted", provenance=_provenance(goal_hash=goal_hash))
        ledger.record_state("golden-work-interrupted", GENERATING, interrupted_work)
        ledger.record_state("golden-work-interrupted", INTERRUPTED, interrupted_work)

        assert ledger.accepted_candidate_for_goal(goal_hash) is None

    def test_a_goal_with_a_real_accepted_candidate_is_blocked(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """Case C: same goal, a prior candidate genuinely reached ACCEPTED
        -- a normal new campaign for the identical goal is refused,
        identified by the real candidate_id that earned it."""
        goal_hash = hash_text("goal already accepted")
        ledger = CandidateLedger(tmp_path / "_ledger")
        _accept(
            ledger, "golden-work-accepted",
            tmp_path / "candidates" / "golden-work-accepted", goal_hash=goal_hash,
        )
        assert ledger.accepted_candidate_for_goal(goal_hash) == "golden-work-accepted"

    def test_a_different_goal_identity_is_never_blocked_by_an_unrelated_acceptance(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """Case D: a real ACCEPTED candidate exists, but for a DIFFERENT
        goal identity -- generation for the new, distinct goal remains
        allowed. Proven with two goals whose only difference is one
        character, so a substring or prefix match could not accidentally
        pass this test."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        accepted_goal_hash = hash_text("goal already accepted")
        _accept(
            ledger, "golden-work-accepted",
            tmp_path / "candidates" / "golden-work-accepted", goal_hash=accepted_goal_hash,
        )
        different_goal_hash = hash_text("goal already accepted ")  # trailing space -> different hash
        assert different_goal_hash != accepted_goal_hash
        assert ledger.accepted_candidate_for_goal(different_goal_hash) is None

    def test_narrative_or_docstring_mentions_of_acceptance_have_no_effect(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """Case E: text alone -- a comment, a candidate_id that merely looks
        like an acceptance claim, a stray file -- must never be read as
        acceptance. Only a real `ACCEPTED` entry in this ledger's own
        append-only history counts. Proven by planting exactly that kind of
        misleading text and confirming it changes nothing."""
        goal_hash = hash_text("goal described as accepted only in prose")
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-claimed-accepted"
        work.mkdir(parents=True)
        _write(work, "NOTES.md", "# golden-work-claimed-accepted\nStatus: ACCEPTED (see team chat)")
        ledger.allocate("golden-work-claimed-accepted", provenance=_provenance(goal_hash=goal_hash))
        ledger.record_state("golden-work-claimed-accepted", GENERATING, work)
        ledger.record_state("golden-work-claimed-accepted", STAGE_FAILED, work)
        assert ledger.accepted_candidate_for_goal(goal_hash) is None


class TestManifestDeterminism:
    def test_the_manifest_is_deterministic_across_repeated_calls(
        self, tmp_path: pathlib.Path,
    ) -> None:
        work = tmp_path / "candidate"
        work.mkdir()
        _write(work, "b.txt", "second")
        _write(work, "a.txt", "first")
        _write(work, "nested/c.txt", "third")

        first = file_manifest(work)
        second = file_manifest(work)
        assert first == second
        assert set(first) == {"b.txt", "a.txt", "nested/c.txt"}

    def test_the_stable_snapshot_subtree_is_excluded(self, tmp_path: pathlib.Path) -> None:
        work = tmp_path / "candidate"
        work.mkdir()
        _write(work, "a.txt", "real model output")
        _write(work, "snapshot/scaffold.txt", "pre-populated baseline, not model output")

        manifest = file_manifest(work)
        assert set(manifest) == {"a.txt"}

    def test_a_symlink_inside_a_candidate_is_never_traversed_or_hashed(
        self, tmp_path: pathlib.Path,
    ) -> None:
        work = tmp_path / "candidate"
        work.mkdir()
        _write(work, "a.txt", "real")
        outside = tmp_path / "outside_secret.txt"
        outside.write_text("must never be read through the candidate")

        try:
            (work / "escape.txt").symlink_to(outside)
        except OSError:
            pytest.skip("this host cannot create symlinks without elevated privileges")

        manifest = file_manifest(work)
        assert "escape.txt" not in manifest
        assert set(manifest) == {"a.txt"}


class TestCandidateReportIsolation:
    def test_one_candidates_history_never_shows_another_candidates_manifest(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """A shared ledger log holds entries for every candidate; a report
        for one identity must never surface another's files."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        work_a = tmp_path / "candidates" / "golden-work-a1"
        work_a.mkdir(parents=True)
        _write(work_a, "App.js", "// candidate A")
        work_b = tmp_path / "candidates" / "golden-work-b1"
        work_b.mkdir(parents=True)
        _write(work_b, "App.js", "// candidate B, unrelated content")

        ledger.allocate("golden-work-a1", provenance=_provenance())
        ledger.record_state("golden-work-a1", GENERATING, work_a)
        ledger.record_state("golden-work-a1", STAGED_GENERATION_PASS, work_a)
        ledger.allocate("golden-work-b1", provenance=_provenance())
        ledger.record_state("golden-work-b1", GENERATING, work_b)
        ledger.record_state("golden-work-b1", STAGED_GENERATION_PASS, work_b)

        latest_a = ledger.latest("golden-work-a1")
        assert latest_a is not None
        manifest_a = latest_a["manifest"]
        manifest_b_sha = file_manifest(work_b)["App.js"]["sha256"]
        assert manifest_a["App.js"]["sha256"] != manifest_b_sha
        assert all(entry["candidate_id"] == "golden-work-a1" for entry in ledger.history("golden-work-a1"))
        assert all(entry["candidate_id"] == "golden-work-b1" for entry in ledger.history("golden-work-b1"))


class TestLegacyClassification:
    def test_a_pre_existing_candidate_with_no_ledger_history_is_legacy_unverified(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """Pre-existing candidates (golden-work-001..124) are never
        retroactively promoted to a verified state just because this
        ledger now exists."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        assert ledger.classify("golden-work-001") == LEGACY_UNVERIFIED

    def test_classification_never_upgrades_without_real_ledger_history(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        work = tmp_path / "candidates" / "golden-work-10"
        work.mkdir(parents=True)
        assert ledger.classify("golden-work-10") == LEGACY_UNVERIFIED
        ledger.allocate("golden-work-10", provenance=_provenance())
        assert ledger.classify("golden-work-10") == ALLOCATED
        ledger.record_state("golden-work-10", GENERATING, work)
        ledger.record_state("golden-work-10", STAGED_GENERATION_PASS, work)
        assert ledger.classify("golden-work-10") == STAGED_GENERATION_PASS
