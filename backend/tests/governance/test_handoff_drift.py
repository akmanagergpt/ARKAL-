"""Negative controls for the handoff drift validator.

Every control mutates an IN-MEMORY copy of the handoff claim block, or an
isolated temporary Git repository. No accepted repository state is modified.

A validator that cannot reject a false claim is not evidence, so each control
asserts that a specific corruption is detected by name.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
VALIDATOR = REPO / "scripts" / "check_handoff.py"
HANDOFF = REPO / "ARKALI_HANDOFF.md"


def load_validator():
    spec = importlib.util.spec_from_file_location("check_handoff", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def drift_names(validator, text: str) -> list[str]:
    return validator.validate(REPO, text).drift


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
        mutated = mutate_claim(handoff_text, "requirements_total", "311")
        assert "requirements total" in drift_names(validator, mutated)

    def test_3b_stale_mandatory_count_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        mutated = mutate_claim(handoff_text, "requirements_mandatory", "300")
        assert "requirements MANDATORY" in drift_names(validator, mutated)

    def test_4_wrong_cumulative_verified_count_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        """cumulative_verified must equal the sum of verified_by_phase."""
        mutated = mutate_claim(handoff_text, "cumulative_verified", "99")
        assert "cumulative verified requirements" in drift_names(validator, mutated)

    def test_5_false_human_gate_acceptance_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        mutated = mutate_claim(
            handoff_text, "accepted_human_gates",
            '["HUMAN_GATE_1", "HUMAN_GATE_2"]',
        )
        assert "accepted human gates" in drift_names(validator, mutated)

    def test_6_wrong_unlocked_phase_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        mutated = mutate_claim(handoff_text, "unlocked_phase", '"9"')
        assert "unlocked phase" in drift_names(validator, mutated)

    def test_6b_wrong_accepted_phase_set_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        mutated = mutate_claim(
            handoff_text, "accepted_phases", '["0", "0A", "0B", "1", "2", "3"]'
        )
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
        mutated = mutate_claim(handoff_text, "next_exact_action_phase", '"23"')
        assert "NEXT EXACT ACTION targets the unlocked phase" in drift_names(
            validator, mutated
        )

    def test_10_stale_adr_status_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        mutated = mutate_claim(handoff_text, "adr_proposed", "9")
        assert "ADR proposed count" in drift_names(validator, mutated)

    def test_10b_stale_adr_accepted_count_is_detected(
        self, validator, handoff_text: str
    ) -> None:
        mutated = mutate_claim(handoff_text, "adr_accepted", "0")
        assert "ADR accepted count" in drift_names(validator, mutated)


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
