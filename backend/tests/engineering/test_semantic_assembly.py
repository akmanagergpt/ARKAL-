from __future__ import annotations

import pathlib
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from arkali.engineering.candidate.assembly import (
    AssemblyCheckResult,
    AssemblyObservation,
    AssemblyReport,
    SemanticAssembler,
)
from arkali.engineering.candidate.assembly_vocabulary import AssemblyVocabulary
from arkali.engineering.candidate.errors import (
    InvalidAssemblyReportError,
    UnknownAssemblyCheckError,
)
from arkali.engineering.candidate.manifest import CandidateComponent, CandidateManifest
from arkali.kernel.contracts.content_address import address_of

REPO = pathlib.Path(__file__).resolve().parents[3]


def candidate() -> CandidateManifest:
    return CandidateManifest.assembled(
        AssemblyVocabulary.load(REPO),
        candidate_id="candidate-12",
        workspace_id="workspace-12",
        task_id="task-12",
        agent_id="agent-12",
        snapshot_ref=address_of(b"snapshot"),
        components=(
            CandidateComponent(
                component="Candidate Products", artifact_ref=address_of(b"product")
            ),
        ),
    )


def evaluators(
    vocabulary: AssemblyVocabulary, *, mismatch: str | None = None
) -> dict[str, Callable[[CandidateManifest], AssemblyObservation]]:
    result: dict[str, Callable[[CandidateManifest], AssemblyObservation]] = {}
    for check in vocabulary.check_ids():
        left = address_of(f"semantic:{check}".encode())
        right = address_of(b"different") if check == mismatch else left
        result[check] = lambda _manifest, left=left, right=right: AssemblyObservation(
            left_ref=left, right_ref=right
        )
    return result


class TestAllCanonicalChecksExecute:
    def test_every_pair_is_executed_in_canonical_order(self) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        report = SemanticAssembler(vocabulary, evaluators(vocabulary)).assemble(candidate())

        assert tuple(item.check for item in report.checks) == vocabulary.check_ids()
        assert report.all_consistent is True
        assert report.manifest_ref == candidate().manifest_ref

    def test_one_mismatch_makes_the_report_inconsistent_without_hiding_other_checks(
        self,
    ) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        mismatch = vocabulary.check_ids()[3]
        report = SemanticAssembler(
            vocabulary, evaluators(vocabulary, mismatch=mismatch)
        ).assemble(candidate())

        assert len(report.checks) == len(vocabulary.check_ids())
        assert tuple(item.check for item in report.checks if not item.consistent) == (
            mismatch,
        )
        assert report.all_consistent is False

    def test_an_evaluator_failure_refuses_the_whole_report(self) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        supplied = evaluators(vocabulary)

        def broken(_manifest: CandidateManifest) -> AssemblyObservation:
            raise RuntimeError("adapter unavailable")

        supplied[vocabulary.check_ids()[0]] = broken
        with pytest.raises(InvalidAssemblyReportError, match="could not be evaluated"):
            SemanticAssembler(vocabulary, supplied).assemble(candidate())


class TestCoverageCannotBeFaked:
    def test_missing_unknown_and_duplicate_evaluators_are_refused(self) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        supplied = evaluators(vocabulary)
        supplied.pop(vocabulary.check_ids()[0])
        with pytest.raises(InvalidAssemblyReportError, match="missing"):
            SemanticAssembler(vocabulary, supplied)
        with pytest.raises(UnknownAssemblyCheckError):
            complete = evaluators(vocabulary)
            SemanticAssembler(
                vocabulary,
                {**complete, "vibes↔hope": next(iter(complete.values()))},
            )
        duplicate = evaluators(vocabulary)
        duplicate[vocabulary.checks()[0]] = duplicate[vocabulary.check_ids()[0]]
        with pytest.raises(InvalidAssemblyReportError, match="duplicate"):
            SemanticAssembler(vocabulary, duplicate)

    def test_a_caller_cannot_assert_a_false_result_or_summary(self) -> None:
        ref = address_of(b"same")
        with pytest.raises(InvalidAssemblyReportError, match="must be derived"):
            AssemblyCheckResult(
                check="api_to_frontend",
                left_ref=ref,
                right_ref=ref,
                consistent=False,
            )
        item = AssemblyCheckResult(
            check="api_to_frontend", left_ref=ref, right_ref=ref, consistent=True
        )
        with pytest.raises(InvalidAssemblyReportError, match="all_consistent"):
            AssemblyReport(
                candidate_id="candidate-12",
                manifest_ref=address_of(b"manifest"),
                checks=(item,),
                all_consistent=False,
            )

    def test_observations_must_be_content_addressed(self) -> None:
        with pytest.raises(InvalidAssemblyReportError, match="content addresses"):
            AssemblyObservation(left_ref="latest", right_ref="latest")


class TestReportArtifact:
    def test_report_is_deterministic_content_addressed_and_immutable(self) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        first = SemanticAssembler(vocabulary, evaluators(vocabulary)).assemble(candidate())
        second = SemanticAssembler(vocabulary, evaluators(vocabulary)).assemble(candidate())

        assert first.rendering() == second.rendering()
        assert first.report_ref == second.report_ref
        with pytest.raises(ValidationError):
            first.all_consistent = False  # type: ignore[misc]

    def test_report_has_no_acceptance_promotion_or_stable_verdict(self) -> None:
        fields = set(AssemblyReport.model_fields)
        assert not fields.intersection({"accepted", "acceptance", "promoted", "stable"})
