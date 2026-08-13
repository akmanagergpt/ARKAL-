"""Phase 13 Package 3: Passport evidence accounting."""

from __future__ import annotations

import pathlib

import pytest

from arkali.acceptance.evidence_graph import evidence_graph
from arkali.acceptance.evidence_passport import evidence_passport
from arkali.evidence.audit.chain import EvidenceInput
from tests.evidence.plane_harness import critical_provenance

REPO = pathlib.Path(__file__).resolve().parents[3]
pytest_plugins = ("tests.evidence.plane_harness",)


def append_evidence(plane: object, requirement_id: str, kind: str, result: str) -> None:
    artifact_id = plane.artifacts.register(  # type: ignore[attr-defined]
        f"{requirement_id}:{kind}:{result}".encode(), critical_provenance()
    )
    plane.evidence.append(  # type: ignore[attr-defined]
        EvidenceInput(
            requirement_id=requirement_id,
            contract_id="C-16",
            artifact_id=artifact_id,
            test_id=kind,
            producer="acceptance.engine",
            result=result,
        )
    )


def test_vocabulary_is_parsed_from_the_frozen_contract() -> None:
    vocabulary = evidence_passport.vocabulary(REPO)
    assert len(vocabulary) == 19
    assert vocabulary[0] == "requirement/specification"
    assert vocabulary[-1] == "final acceptance"


@pytest.mark.parametrize("kinds", [("one",), ("one", "two", "three")])
def test_vocabulary_size_follows_authority(
    tmp_path: pathlib.Path, kinds: tuple[str, ...]
) -> None:
    target = tmp_path / "docs" / "ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "## Proof-of-Engineering Passport\n"
        f"Every critical capability records applicable: {', '.join(kinds)}.\n",
        encoding="utf-8",
    )
    assert evidence_passport.vocabulary(tmp_path) == kinds


def test_passport_groups_register_obligations_by_capability(plane: object) -> None:
    with plane.session() as opened:  # type: ignore[attr-defined]
        append_evidence(opened, "ARK-REQ-0069", "integ", "PASS")
        append_evidence(opened, "ARK-REQ-0069", "prov", "PASS")
        graph = evidence_graph.derive(opened.evidence, REPO)
        passport = evidence_passport.build(graph, REPO, {})

    engine = next(
        item for item in passport.capabilities
        if item.capability == "acceptance.engine"
    )
    requirement = next(
        item for item in engine.requirements
        if item.requirement_id == "ARK-REQ-0069"
    )
    assert requirement.evidence_complete
    assert requirement.required_evidence == ("integ", "prov")
    assert requirement.missing_evidence == ()
    assert {item.evidence_kind for item in requirement.bindings} == {"integ", "prov"}
    assert all(item.evidence_id and item.artifact_id for item in requirement.bindings)
    assert passport.requirement_denominator == 311


def test_missing_or_non_pass_evidence_remains_explicit(plane: object) -> None:
    with plane.session() as opened:  # type: ignore[attr-defined]
        append_evidence(opened, "ARK-REQ-0069", "integ", "FAIL")
        graph = evidence_graph.derive(opened.evidence, REPO)
        passport = evidence_passport.build(graph, REPO, {})
    engine = next(
        item for item in passport.capabilities
        if item.capability == "acceptance.engine"
    )
    requirement = next(
        item for item in engine.requirements
        if item.requirement_id == "ARK-REQ-0069"
    )
    assert not requirement.evidence_complete
    assert requirement.present_evidence == ()
    assert requirement.missing_evidence == ("integ", "prov")
    assert requirement.bindings == ()


def test_capability_completion_counts_evidence_complete_requirements(plane: object) -> None:
    with plane.session() as opened:  # type: ignore[attr-defined]
        append_evidence(opened, "ARK-REQ-0069", "integ", "PASS")
        append_evidence(opened, "ARK-REQ-0069", "prov", "PASS")
        graph = evidence_graph.derive(opened.evidence, REPO)
        passport = evidence_passport.build(graph, REPO, {})
    engine = next(
        item for item in passport.capabilities
        if item.capability == "acceptance.engine"
    )
    assert engine.requirement_numerator == 1
    assert passport.completion_fraction == (1, 311)
