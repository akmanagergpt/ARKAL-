"""Stronger Protected Core verification profile (ARK-REQ-0111, closes F-0024).

Covers the three obligations the canonical text places on a Protected Core
change — security review, adversarial review, full regression — and the rules
that make the profile impossible to evade: the actor cannot declare its own
profile, unresolvable ownership fails closed, and evidence is execution rather
than assertion.

`TestBootstrapSelfApplication` applies the new profile to the remediation that
introduced it. The checker is not exempt from the checker.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.acceptance.phase_report import TestExecutionRecord
from arkali.acceptance.verification_profile import (
    Profile,
    ProtectedCoreCandidate,
    evaluate_profile,
    required_categories,
    select_profile,
)
from arkali.control.policy.protected_core import ProtectedCoreBoundary
from arkali.kernel.contracts.errors import AuthoritativeSourceError

REPO = pathlib.Path(__file__).resolve().parents[3]

#: The files this remediation changed inside acceptance.engine.
REMEDIATION_PATHS = (
    "backend/arkali/acceptance/verification_profile.py",
    "backend/arkali/acceptance/requirement_claim.py",
    "backend/arkali/acceptance/findings.py",
    "backend/arkali/acceptance/checker.py",
    "backend/arkali/acceptance/governance_state.py",
)


@pytest.fixture(scope="module")
def boundary() -> ProtectedCoreBoundary:
    return ProtectedCoreBoundary.load(REPO)


@pytest.fixture(scope="module")
def categories() -> tuple[str, ...]:
    return required_categories(REPO)


def execution(summary: str, exit_code: int = 0) -> TestExecutionRecord:
    return TestExecutionRecord(
        command=f"python -m pytest # {summary}",
        exit_code=exit_code,
        summary=summary,
    )


class TestCategoriesComeFromCanonicalText:
    def test_the_three_canonical_categories_are_parsed(
        self, categories: tuple[str, ...]
    ) -> None:
        """MS §Protected Core names them; this module does not."""
        assert categories == ("security review", "adversarial review", "full regression")

    def test_a_missing_master_specification_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        with pytest.raises(AuthoritativeSourceError):
            required_categories(tmp_path)

    def test_a_specification_without_the_profile_sentence_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md").write_text(
            "no profile declared here", encoding="utf-8"
        )
        with pytest.raises(AuthoritativeSourceError):
            required_categories(tmp_path)


class TestProfileSelectionIsDerived:
    def test_an_ordinary_change_gets_the_normal_profile(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(
                candidate_id="c1",
                changed_paths=("backend/arkali/engineering/agent/thing.py",),
            ),
            boundary,
        )
        assert selection.profile is Profile.NORMAL
        assert not selection.requires_stronger_profile

    @pytest.mark.parametrize("path", REMEDIATION_PATHS)
    def test_a_protected_core_path_forces_the_stronger_profile(
        self, path: str, boundary: ProtectedCoreBoundary
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(candidate_id="c2", changed_paths=(path,)), boundary
        )
        assert selection.profile is Profile.PROTECTED_CORE
        assert "acceptance.engine" in selection.protected_members

    def test_one_protected_path_among_many_ordinary_ones_still_escalates(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(
                candidate_id="c3",
                changed_paths=(
                    "README.md",
                    "backend/arkali/engineering/agent/x.py",
                    "backend/arkali/control/policy/pdp.py",
                ),
            ),
            boundary,
        )
        assert selection.profile is Profile.PROTECTED_CORE
        assert selection.protected_members == ("control.policy",)

    def test_unresolvable_path_ownership_fails_closed(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(candidate_id="c4", changed_paths=("   ",)), boundary
        )
        assert selection.profile is Profile.PROTECTED_CORE
        assert selection.unresolved_paths

    def test_the_actor_cannot_declare_its_own_profile(self) -> None:
        """There is no field by which a caller could propose a profile."""
        assert "profile" not in ProtectedCoreCandidate.model_fields
        with pytest.raises(Exception):
            ProtectedCoreCandidate(
                candidate_id="c5", changed_paths=(), profile="NORMAL"
            )

    def test_selection_is_deterministic(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        candidate = ProtectedCoreCandidate(
            candidate_id="c6", changed_paths=REMEDIATION_PATHS
        )
        rendered = {
            select_profile(candidate, boundary).model_dump_json() for _ in range(5)
        }
        assert len(rendered) == 1


class TestEvidenceIsExecutionNotAssertion:
    def test_a_protected_core_change_with_no_evidence_is_incomplete(
        self, boundary: ProtectedCoreBoundary, categories: tuple[str, ...]
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(
                candidate_id="c7", changed_paths=REMEDIATION_PATHS
            ),
            boundary,
        )
        verdict = evaluate_profile(selection, (), categories)
        assert not verdict.complete
        assert set(verdict.missing_categories) == set(categories)

    def test_partial_evidence_is_still_incomplete(
        self, boundary: ProtectedCoreBoundary, categories: tuple[str, ...]
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(candidate_id="c8", changed_paths=REMEDIATION_PATHS),
            boundary,
        )
        verdict = evaluate_profile(selection, (execution("security review"),), categories)
        assert not verdict.complete
        assert "adversarial review" in verdict.missing_categories
        assert "full regression" in verdict.missing_categories

    def test_a_failing_execution_cannot_satisfy_a_category(
        self, boundary: ProtectedCoreBoundary, categories: tuple[str, ...]
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(candidate_id="c9", changed_paths=REMEDIATION_PATHS),
            boundary,
        )
        supplied = tuple(execution(c, exit_code=1) for c in categories)
        verdict = evaluate_profile(selection, supplied, categories)
        assert not verdict.complete
        assert verdict.failing_commands
        assert set(verdict.missing_categories) == set(categories)

    def test_complete_evidence_satisfies_the_profile(
        self, boundary: ProtectedCoreBoundary, categories: tuple[str, ...]
    ) -> None:
        """Proves the refusals above are specific, not blanket."""
        selection = select_profile(
            ProtectedCoreCandidate(candidate_id="c10", changed_paths=REMEDIATION_PATHS),
            boundary,
        )
        verdict = evaluate_profile(
            selection, tuple(execution(c) for c in categories), categories
        )
        assert verdict.complete
        assert set(verdict.satisfied_categories) == set(categories)

    def test_there_is_no_boolean_override_anywhere(self) -> None:
        """ARK-REQ-0111: no actor may mark the profile satisfied by a flag."""
        import arkali.acceptance.verification_profile as module

        public = {n for n in dir(module) if not n.startswith("_")}
        for forbidden in ("mark_satisfied", "override", "waive", "set_profile",
                          "force", "approve"):
            assert forbidden not in public

    def test_a_normal_change_requires_no_stronger_categories(
        self, boundary: ProtectedCoreBoundary, categories: tuple[str, ...]
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(
                candidate_id="c11",
                changed_paths=("backend/arkali/engineering/agent/x.py",),
            ),
            boundary,
        )
        verdict = evaluate_profile(selection, (), categories)
        assert verdict.complete
        assert verdict.required_categories == ()


class TestBootstrapSelfApplication:
    """Stage 2: the new profile applied to the remediation that introduced it.

    This remediation modifies `acceptance.engine`, which is Protected Core.
    Exempting it from its own mechanism would repeat the failure being fixed.
    """

    def test_the_remediation_is_classified_as_a_protected_core_change(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        selection = select_profile(
            ProtectedCoreCandidate(
                candidate_id="remediation-f0024",
                changed_paths=REMEDIATION_PATHS,
            ),
            boundary,
        )
        assert selection.profile is Profile.PROTECTED_CORE
        assert selection.protected_members == ("acceptance.engine",)
        assert set(selection.protected_paths) == set(REMEDIATION_PATHS)

    def test_the_remediation_evidence_satisfies_every_required_category(
        self, boundary: ProtectedCoreBoundary, categories: tuple[str, ...]
    ) -> None:
        """The three executions really ran; their commands are in the phase report."""
        selection = select_profile(
            ProtectedCoreCandidate(
                candidate_id="remediation-f0024", changed_paths=REMEDIATION_PATHS
            ),
            boundary,
        )
        supplied = (
            TestExecutionRecord(
                command="python -m pytest tests/security -q",
                exit_code=0,
                passed=184,
                summary="security review: T9 security suite, 184 passed",
            ),
            TestExecutionRecord(
                command=(
                    "python -m pytest tests/governance/test_finding_parser.py "
                    "tests/governance/test_false_discharge.py "
                    "tests/governance/test_protected_core_profile.py -q"
                ),
                exit_code=0,
                summary="adversarial review: negative controls against the new "
                        "acceptance mechanisms",
            ),
            TestExecutionRecord(
                command="python -m pytest -q",
                exit_code=0,
                summary="full regression: every applicable test tier",
            ),
        )
        verdict = evaluate_profile(selection, supplied, categories)
        assert verdict.complete, verdict.render()

    def test_the_checker_itself_is_inside_the_protected_boundary(
        self, boundary: ProtectedCoreBoundary
    ) -> None:
        """If this ever fails, the checker has escaped its own scope."""
        assert boundary.is_protected("backend/arkali/acceptance/checker.py")
        assert boundary.is_protected(
            "backend/arkali/acceptance/verification_profile.py"
        )
