"""Negative controls for the handoff drift validator.

Every control mutates an IN-MEMORY copy of the handoff claim block, or an
isolated temporary Git repository. No accepted repository state is modified.

A validator that cannot reject a false claim is not evidence, so each control
asserts that a specific corruption is detected by name.

The two halves F-0047 added live beside this module rather than in it, because
it was at its 400 logical-line budget: `test_handoff_architecture_drift.py`
covers the live architecture summary and `test_handoff_self_reference.py` covers
the manifest's own commit references. All three share `handoff_harness.py`, so
the validator is loaded in one place.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess

import pytest

from arkali.acceptance.governance_state import GovernanceState
from tests.governance.handoff_harness import (
    HANDOFF,
    REPO,
    drift_names,
    load_validator,
)


@pytest.fixture(scope="module")
def validator():
    return load_validator()


@pytest.fixture(scope="module")
def handoff_text() -> str:
    return HANDOFF.read_text(encoding="utf-8")


def mutate_claim(text: str, key: str, new_value: str) -> str:
    """Replace one claim line inside the claim block. In memory only."""
    pattern = re.compile(rf"^({re.escape(key)}:).*$", re.M)
    mutated, count = pattern.subn(rf"\1 {new_value}", text)
    assert count >= 1, f"claim {key!r} not found in the handoff"
    return mutated


def truth(validator) -> dict:
    """Live derived truth. Mutations are built from this, never hard-coded.

    Defect F-0021: several controls asserted that a *literal* value was wrong -
    `accepted_phases: ["0","0A","0B","1","2","3"]`, `unlocked_phase: "9"`,
    `accepted_human_gates: [... ,"HUMAN_GATE_2"]`. Each of those becomes true as
    the build progresses, at which point the control stops testing detection and
    starts failing for a reason unrelated to the validator. A negative control
    whose expected-wrong value can become right has an expiry date. Deriving the
    mutation from current truth removes it.
    """
    return validator.derive_truth(REPO)


def a_phase_that_is_not_accepted(validator) -> str:
    """A phase id guaranteed absent from the accepted set, derived at run time."""
    current = truth(validator)
    unlocked = current["unlocked_phase"]
    if unlocked and unlocked not in current["accepted_phases"]:
        return unlocked
    candidates = [str(n) for n in range(37, 0, -1)]
    for candidate in candidates:
        if candidate not in current["accepted_phases"]:
            return candidate
    raise AssertionError("every phase is accepted; control cannot be constructed")


class TestHandoffAgreesWithRepository:
    def test_live_handoff_has_no_governance_drift(
        self, validator, handoff_text: str
    ) -> None:
        """The committed handoff must agree with the repository.

        The working-tree claim is excluded here: it is legitimately false while
        uncommitted changes are in flight, and is asserted separately by the
        committed-state check in CI.
        """
        drift = [d for d in drift_names(validator, handoff_text)
                 if d != "working-tree clean claim"]
        assert drift == [], f"unexpected governance drift: {drift}"


class TestNegativeControls:
    """Ten required defect classes, each proven detectable."""

    def test_1_stale_head_is_detected(self, validator, handoff_text: str) -> None:
        baseline = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=REPO, capture_output=True, text=True,
        ).stdout.strip().splitlines()[0]
        mutated = mutate_claim(handoff_text, "head", baseline)
        assert "HEAD is current or a governed-clean ancestor" in drift_names(
            validator, mutated
        )

    def test_2_wrong_branch_is_detected(self, validator, handoff_text: str) -> None:
        mutated = mutate_claim(handoff_text, "branch", "not-a-branch")
        assert "branch" in drift_names(validator, mutated)

    def test_3_stale_requirement_count_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        wrong = truth(validator)["requirements_total"] - 2
        mutated = mutate_claim(handoff_text, "requirements_total", str(wrong))
        assert "requirements total" in drift_names(validator, mutated)

    def test_3b_stale_mandatory_count_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        wrong = truth(validator)["requirements_mandatory"] - 3
        mutated = mutate_claim(handoff_text, "requirements_mandatory", str(wrong))
        assert "requirements MANDATORY" in drift_names(validator, mutated)

    def test_4_wrong_cumulative_verified_count_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        """cumulative_verified must equal the sum of verified_by_phase."""
        claims = validator.parse_claims(handoff_text)
        wrong = sum(int(v) for v in (claims.get("verified_by_phase") or {}).values()) + 1
        mutated = mutate_claim(handoff_text, "cumulative_verified", str(wrong))
        assert "cumulative verified requirements" in drift_names(validator, mutated)

    def test_5_false_human_gate_acceptance_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        """Claims one more gate than is recorded, whichever gates those are."""
        accepted = list(truth(validator)["accepted_human_gates"])
        unaccepted = next(
            f"HUMAN_GATE_{n}" for n in range(1, 9)
            if f"HUMAN_GATE_{n}" not in accepted
        )
        claimed = json.dumps(sorted([*accepted, unaccepted]))
        mutated = mutate_claim(handoff_text, "accepted_human_gates", claimed)
        assert "accepted human gates" in drift_names(validator, mutated)

    def test_6_wrong_unlocked_phase_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        actual = truth(validator)["unlocked_phase"]
        wrong = next(str(n) for n in range(37, 0, -1) if str(n) != actual)
        mutated = mutate_claim(handoff_text, "unlocked_phase", f'"{wrong}"')
        assert "unlocked phase" in drift_names(validator, mutated)

    def test_6b_wrong_accepted_phase_set_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        """Adds a phase that is provably not accepted right now."""
        current = truth(validator)
        claimed = json.dumps(
            sorted([*current["accepted_phases"], a_phase_that_is_not_accepted(validator)])
        )
        mutated = mutate_claim(handoff_text, "accepted_phases", claimed)
        assert "accepted phases" in drift_names(validator, mutated)

    def test_7_missing_authoritative_source_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        mutated = handoff_text.replace(
            "  - docs/build/BUILD_STATE.md",
            "  - docs/build/BUILD_STATE.md\n  - docs/does_not_exist.md",
        )
        assert "all authoritative sources exist" in drift_names(validator, mutated)

    def test_8_false_clean_tree_claim_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        """A clean claim must be rejected when the tree is genuinely dirty.

        The probe file must NOT be gitignored, or the tree stays clean and this
        control passes for the wrong reason. An earlier version used a `.tmp`
        suffix, which `.gitignore` excludes; it only appeared to work because
        unrelated uncommitted files happened to be present at the time.
        """
        probe = REPO / "_handoff_dirty_probe_do_not_commit.md"
        assert subprocess.run(
            ["git", "check-ignore", "-q", "--", probe.name],
            cwd=REPO, capture_output=True,
        ).returncode != 0, "probe file is gitignored; the control would be vacuous"
        try:
            probe.write_text("dirty-tree probe", encoding="utf-8")
            dirty = subprocess.run(
                ["git", "status", "--porcelain", "-uall"],
                cwd=REPO, capture_output=True, text=True,
            ).stdout
            assert probe.name in dirty, "probe did not dirty the working tree"
            mutated = mutate_claim(handoff_text, "working_tree_clean", "true")
            assert "working-tree clean claim" in drift_names(validator, mutated)
        finally:
            if probe.exists():
                probe.unlink()

    def test_9_next_action_pointing_at_wrong_phase_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        actual = truth(validator)["unlocked_phase"]
        wrong = next(str(n) for n in range(37, 0, -1) if str(n) != actual)
        mutated = mutate_claim(handoff_text, "next_exact_action_phase", f'"{wrong}"')
        assert "NEXT EXACT ACTION targets the unlocked phase" in drift_names(
            validator, mutated
        )

    def test_10_stale_adr_status_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        wrong = truth(validator)["adr_proposed"] + 9
        mutated = mutate_claim(handoff_text, "adr_proposed", str(wrong))
        assert "ADR proposed count" in drift_names(validator, mutated)

    def test_10b_stale_adr_accepted_count_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        wrong = truth(validator)["adr_accepted"] + 1
        mutated = mutate_claim(handoff_text, "adr_accepted", str(wrong))
        assert "ADR accepted count" in drift_names(validator, mutated)


class TestControlsDoNotDecay:
    """Permanent guard for defect class F-0021.

    A negative control must assert that a *derived-wrong* value is detected, not
    that a *literal* value is wrong. Literals expire: `unlocked_phase: "9"` is
    wrong today and correct at Phase 9, and on that day the control stops
    proving detection and starts reporting a failure that has nothing to do with
    the validator.

    These checks re-derive each mutation and assert it still differs from truth.
    """

    def test_phase_mutations_still_differ_from_truth(self, validator) -> None:
        current = truth(validator)
        assert a_phase_that_is_not_accepted(validator) not in current["accepted_phases"]

    def test_unlocked_phase_mutation_still_differs_from_truth(self, validator) -> None:
        actual = truth(validator)["unlocked_phase"]
        wrong = next(str(n) for n in range(37, 0, -1) if str(n) != actual)
        assert wrong != actual

    def test_human_gate_mutation_still_differs_from_truth(self, validator) -> None:
        accepted = list(truth(validator)["accepted_human_gates"])
        unaccepted = next(
            f"HUMAN_GATE_{n}" for n in range(1, 9)
            if f"HUMAN_GATE_{n}" not in accepted
        )
        assert unaccepted not in accepted

    def test_count_mutations_still_differ_from_truth(self, validator) -> None:
        current = truth(validator)
        assert current["requirements_total"] - 2 != current["requirements_total"]
        assert current["adr_accepted"] + 1 != current["adr_accepted"]
        assert current["adr_proposed"] + 9 != current["adr_proposed"]


class TestCurrentPhaseDerivationIgnoresProse:
    """F-0034. The current work phase is read from declared state, not prose.

    `derive_truth` selected the unlocked phase with
    `"UNLOCKED" in status.status_text.upper()`, the same substring habit that let
    commentary decide acceptance. A row that merely *mentions* an unlocked phase
    would have matched, and two matches collapse `unlocked_phase` to None - so a
    sentence added to an unrelated row could silently break the manifest.

    The temp repository is a copy; no governed file is written.
    """

    @staticmethod
    def _repo_copy(tmp_path: pathlib.Path) -> pathlib.Path:
        for relative in (
            "docs/build/BUILD_STATE.md",
            "docs/build/OPEN_BLOCKERS.md",
            "docs/acceptance/HUMAN_GATE_RECORDS.md",
            "docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md",
        ):
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                (REPO / relative).read_text(encoding="utf-8"), encoding="utf-8"
            )
        return tmp_path

    def _unlocked_phase(self, root: pathlib.Path) -> str | None:
        state = GovernanceState.load(root)
        found = [
            pid for pid, status in state.phases.items()
            if status.is_unlocked and not status.is_accepted
        ]
        return found[0] if len(found) == 1 else None

    def test_prose_mentioning_unlocked_on_another_row_changes_nothing(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = self._repo_copy(tmp_path)
        build_state = root / "docs/build/BUILD_STATE.md"
        before = self._unlocked_phase(root)
        assert before is not None, "fixture must start from a resolvable phase"

        original = build_state.read_text(encoding="utf-8")
        accepted_row = next(
            line for line in original.splitlines()
            if line.startswith("| 1 |") and "MACHINE-ACCEPTED" in line
        )
        # An accepted phase's row now also mentions unlockedness in commentary.
        injected = accepted_row.rstrip("| ") + " This phase UNLOCKED the next one. |"
        build_state.write_text(
            original.replace(accepted_row, injected, 1), encoding="utf-8"
        )

        assert self._unlocked_phase(root) == before, (
            "commentary on an unrelated row moved the current work phase"
        )

    def test_a_second_declared_unlocked_phase_is_still_ambiguous(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The derivation must stay strict: it is prose it ignores, not state."""
        root = self._repo_copy(tmp_path)
        build_state = root / "docs/build/BUILD_STATE.md"
        original = build_state.read_text(encoding="utf-8")
        accepted_row = next(
            line for line in original.splitlines()
            if line.startswith("| 1 |") and "MACHINE-ACCEPTED" in line
        )
        second = "| 1 | Repository Bootstrap | **UNLOCKED — NOT_STARTED** |"
        build_state.write_text(
            original.replace(accepted_row, second, 1), encoding="utf-8"
        )
        assert self._unlocked_phase(root) is None


class TestFailClosed:
    def test_missing_claim_block_is_rejected(self, validator) -> None:
        with pytest.raises(ValueError):
            validator.parse_claims("# a handoff with no claim block\n")

    def test_non_mapping_claim_block_is_rejected(self, validator) -> None:
        with pytest.raises(ValueError):
            validator.parse_claims(
                "```yaml\n# ARKALI-HANDOFF-CLAIMS\n- just\n- a\n- list\n```"
            )

    def test_open_blocker_high_claim_is_checked(
        self, validator, handoff_text: str
    ) -> None:
        mutated = mutate_claim(handoff_text, "open_blocker_high", '["EXT-999"]')
        assert "open BLOCKER/HIGH" in drift_names(validator, mutated)

    def test_wrong_schema_version_is_rejected(
        self, validator, handoff_text: str
    ) -> None:
        mutated = mutate_claim(handoff_text, "schema_version", "ARKALI-HANDOFF-V0")
        assert "schema version" in drift_names(validator, mutated)


class TestNoRepositoryMutation:
    def test_validation_does_not_modify_accepted_state(self, validator) -> None:
        watched = [
            HANDOFF,
            REPO / "docs" / "canonical" / "AUTHORITY_MAP.yaml",
            REPO / "docs" / "canonical" / "REQUIREMENT_REGISTER.md",
            REPO / "docs" / "build" / "BUILD_STATE.md",
            REPO / "docs" / "acceptance" / "HUMAN_GATE_RECORDS.md",
        ]
        before = {p: p.read_bytes() for p in watched}
        validator.validate(REPO, HANDOFF.read_text(encoding="utf-8"))
        assert {p: p.read_bytes() for p in watched} == before


class TestSessionPrompt:
    def test_prompt_exists_and_names_the_validator(self) -> None:
        prompt = (REPO / "ARKALI_NEW_SESSION_PROMPT.txt").read_text(encoding="utf-8")
        assert "scripts/check_handoff.py" in prompt
        assert "HANDOFF_DRIFT" in prompt
        assert "repository" in prompt.lower()

    def test_prompt_contains_no_secret_or_personal_data(self) -> None:
        prompt = (REPO / "ARKALI_NEW_SESSION_PROMPT.txt").read_text(encoding="utf-8")
        assert not re.search(
            r"(?i)(api[_-]?key|password|secret\s*[:=]|@gmail\.|BEGIN [A-Z ]*PRIVATE KEY)",
            prompt,
        )

    def test_missing_prompt_is_detected(
        self, validator, handoff_text: str, tmp_path: pathlib.Path
    ) -> None:
        absent = tmp_path / "no_such_prompt.txt"
        report = validator.validate(REPO, handoff_text, session_prompt=absent)
        assert "new-session prompt present" in report.drift
