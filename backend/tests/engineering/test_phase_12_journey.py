"""Phase 12 composed journey: stable snapshot to assembled candidate.

The journey composes the real Package 1--4 mechanisms.  It deliberately stops
at assembly: verification, acceptance and promotion remain later authorities.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable

import pytest

from arkali.control.policy.agent_authority import AgentAuthority
from arkali.control.policy.policy_errors import DirectStableMutationError
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.candidate.assembly import AssemblyObservation, SemanticAssembler
from arkali.engineering.candidate.assembly_vocabulary import AssemblyVocabulary
from arkali.engineering.candidate.manifest import CandidateComponent, CandidateManifest
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.kernel.contracts.content_address import address_of
from arkali.lifecycle.release.stable_path import StableCandidatePath, StablePathError

REPO = pathlib.Path(__file__).resolve().parents[3]
PHASE = "12"


def _evaluators(
    vocabulary: AssemblyVocabulary, semantic_ref: str
) -> dict[str, Callable[[CandidateManifest], AssemblyObservation]]:
    return {
        check: (
            lambda _manifest, ref=semantic_ref: AssemblyObservation(
                left_ref=ref, right_ref=ref
            )
        )
        for check in vocabulary.check_ids()
    }


class TestPhase12Journey:
    def test_stable_source_is_copied_into_one_exclusive_workspace(
        self, tmp_path: pathlib.Path
    ) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        source = REPO / "docs/contracts/candidate.md"
        (stable / "candidate.md").write_bytes(source.read_bytes())
        original = (stable / "candidate.md").read_bytes()

        workspace = WorkspaceAuthority(tmp_path / "ephemeral").allocate(
            workspace_id="phase-12-workspace",
            task_id="phase-12-task",
            agent_id="implementation-agent",
            stable_snapshot=stable,
        )
        workspace.write("snapshot/candidate.md", original + b"\nassembled candidate\n")

        assert (stable / "candidate.md").read_bytes() == original
        assert workspace.snapshot.joinpath("candidate.md").read_bytes() != original

    def test_real_candidate_bytes_bind_manifest_and_every_semantic_check(
        self, tmp_path: pathlib.Path
    ) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        stable = tmp_path / "stable"
        stable.mkdir()
        source_bytes = (REPO / "docs/contracts/candidate.md").read_bytes()
        (stable / "candidate.md").write_bytes(source_bytes)
        workspace = WorkspaceAuthority(tmp_path / "ephemeral").allocate(
            workspace_id="phase-12-workspace",
            task_id="phase-12-task",
            agent_id="implementation-agent",
            stable_snapshot=stable,
        )
        candidate_bytes = source_bytes + b"\nsemantic candidate\n"
        workspace.write("snapshot/candidate.md", candidate_bytes)
        semantic_ref = address_of(candidate_bytes)
        manifest = CandidateManifest.assembled(
            vocabulary,
            candidate_id="phase-12-candidate",
            workspace_id=workspace.workspace_id,
            task_id=workspace.task_id,
            agent_id=workspace.agent_id,
            snapshot_ref=address_of(source_bytes),
            components=(
                CandidateComponent(
                    component="Candidate Products", artifact_ref=semantic_ref
                ),
            ),
        )

        report = SemanticAssembler(
            vocabulary, _evaluators(vocabulary, semantic_ref)
        ).assemble(manifest)

        assert report.candidate_id == manifest.candidate_id
        assert report.manifest_ref == manifest.manifest_ref
        assert tuple(result.check for result in report.checks) == vocabulary.check_ids()
        assert report.all_consistent
        assert report.report_ref == address_of(report.rendering())

    def test_direct_stable_mutation_and_stage_skips_are_refused(self) -> None:
        authority = AgentAuthority.load(REPO)
        for actor in (*authority.barred_actors(), "invented actor"):
            with pytest.raises(DirectStableMutationError):
                authority.assert_may_directly_mutate_stable(actor)

        path = StableCandidatePath.load(REPO)
        receipt = path.begin_candidate(candidate_id="phase-12-candidate")
        with pytest.raises(StablePathError):
            path.advance(receipt, to_stage=path.stages()[-1])
        assert receipt.stage == path.stages()[1]

    def test_assembly_does_not_claim_verification_acceptance_or_promotion(self) -> None:
        forbidden = {"verified", "verification", "accepted", "acceptance", "promoted", "stable"}
        assert forbidden.isdisjoint(CandidateManifest.model_fields)
        from arkali.engineering.candidate.assembly import AssemblyReport

        assert forbidden.isdisjoint(AssemblyReport.model_fields)

    def test_denominator_is_derived_and_owned_by_three_contexts(self) -> None:
        requirements = RequirementRegister.load(REPO).for_phase(PHASE)
        assert {item.req_id for item in requirements} == {
            "ARK-REQ-0005",
            "ARK-REQ-0023",
            "ARK-REQ-0024",
            "ARK-REQ-0025",
            "ARK-REQ-0056",
            "ARK-REQ-0058",
            "ARK-REQ-0212",
        }
        assert {item.owning_component for item in requirements} == {
            "engineering.candidate",
            "lifecycle.release",
            "control.policy",
        }
