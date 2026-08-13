"""Phase 13 Package 5: evidence-derived Acceptance Engine verdict."""

from __future__ import annotations

import pathlib

import pytest

from arkali.acceptance.evidence_graph import evidence_graph
from arkali.acceptance.evidence_passport import evidence_passport
from arkali.control.policy.acceptance_boundary import AcceptanceBoundaryPolicy
from arkali.control.policy.policy_errors import HumanGateNotRecorded
from arkali.evidence.audit.chain import EvidenceInput
from tests.evidence.plane_harness import critical_provenance

REPO = pathlib.Path(__file__).resolve().parents[3]
pytest_plugins = ("tests.evidence.plane_harness",)


def append_evidence(plane: object, requirement_id: str, kind: str) -> None:
    artifact_id = plane.artifacts.register(  # type: ignore[attr-defined]
        f"{requirement_id}:{kind}".encode(), critical_provenance()
    )
    plane.evidence.append(  # type: ignore[attr-defined]
        EvidenceInput(
            requirement_id=requirement_id,
            contract_id="C-16",
            artifact_id=artifact_id,
            test_id=kind,
            producer="acceptance.engine",
            result="PASS",
        )
    )


def build_passport(plane: object, evidence: tuple[tuple[str, str], ...]) -> object:
    with plane.session() as opened:  # type: ignore[attr-defined]
        for requirement_id, kind in evidence:
            append_evidence(opened, requirement_id, kind)
        graph = evidence_graph.derive(opened.evidence, REPO)
        return evidence_passport.build(graph, REPO, {})


def test_implementation_evidence_is_not_verification(plane: object) -> None:
    passport = build_passport(plane, (("ARK-REQ-0069", "integ"),))
    verdict = evidence_passport.verdict(
        passport, "acceptance.engine", REPO
    )
    assert verdict.implemented
    assert not verdict.verified
    assert verdict.result == "IMPLEMENTED_NOT_VERIFIED"
    assert "ARK-REQ-0069:prov" in verdict.missing_evidence


def test_no_passing_binding_is_not_implemented_or_verified(plane: object) -> None:
    passport = build_passport(plane, (("ARK-REQ-0038", "sec"),))
    verdict = evidence_passport.verdict(
        passport, "acceptance.engine", REPO
    )
    assert not verdict.implemented
    assert not verdict.verified
    assert verdict.result == "NOT_VERIFIED"


def test_all_register_obligations_are_required_for_verified(plane: object) -> None:
    seed = build_passport(plane, (("ARK-REQ-0069", "integ"),))
    account = next(item for item in seed.capabilities if item.capability == "acceptance.engine")
    evidence = tuple(
        (requirement.requirement_id, kind)
        for requirement in account.requirements
        for kind in requirement.required_evidence
    )
    complete = build_passport(plane, evidence)
    verdict = evidence_passport.verdict(complete, "acceptance.engine", REPO)
    assert verdict.implemented and verdict.verified
    assert verdict.result == "VERIFIED"
    assert verdict.missing_requirements == ()
    assert verdict.missing_evidence == ()


def test_passport_summary_cannot_be_forged_into_verified(plane: object) -> None:
    passport = build_passport(plane, (("ARK-REQ-0069", "integ"),))
    account = next(item for item in passport.capabilities if item.capability == "acceptance.engine")
    forged_requirement = account.requirements[0].model_copy(update={"missing_evidence": ()})
    forged_account = account.model_copy(
        update={
            "requirements": (forged_requirement, *account.requirements[1:]),
            "requirement_numerator": account.requirement_denominator,
        }
    )
    forged = passport.model_copy(
        update={
            "capabilities": tuple(
                forged_account if item.capability == account.capability else item
                for item in passport.capabilities
            )
        }
    )
    with pytest.raises(evidence_graph.Refusal, match="not reconciled"):
        evidence_passport.verdict(forged, "acceptance.engine", REPO)


def test_required_human_gate_is_enforced_by_policy(plane: object) -> None:
    passport = build_passport(plane, (("ARK-REQ-0069", "integ"),))
    gate = AcceptanceBoundaryPolicy.load(REPO).human_gates()[0]
    with pytest.raises(HumanGateNotRecorded, match=gate):
        evidence_passport.verdict(
            passport, "acceptance.engine", REPO, required_human_gate=gate
        )
    verdict = evidence_passport.verdict(
        passport,
        "acceptance.engine",
        REPO,
        required_human_gate=gate,
        recorded_human_gates=(gate,),
    )
    assert not verdict.verified and verdict.required_human_gate == gate


def test_unknown_or_vacuous_capability_fails_closed(plane: object) -> None:
    passport = build_passport(plane, (("ARK-REQ-0069", "integ"),))
    with pytest.raises(evidence_graph.Refusal, match="no unique"):
        evidence_passport.verdict(passport, "not.registered", REPO)
