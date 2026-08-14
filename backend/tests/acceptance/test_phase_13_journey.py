"""Phase 13 composed journey: intact evidence to independent verdict.

The journey composes the real C-15 store with C-16, register-derived coverage,
Passport accounting and the policy-owned machine/human boundary.  It creates no
evidence outside the test and grants no release or Stable authority.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.acceptance.evidence_graph import evidence_graph
from arkali.acceptance.evidence_passport import evidence_passport
from arkali.control.policy.acceptance_boundary import AcceptanceBoundaryPolicy
from arkali.control.policy.policy_errors import HumanGateNotRecorded
from arkali.control.specification.register_parser import RequirementRegister
from arkali.evidence.audit.chain import EvidenceInput
from tests.evidence.plane_harness import critical_provenance

REPO = pathlib.Path(__file__).resolve().parents[3]
PHASE = "13"
pytest_plugins = ("tests.evidence.plane_harness",)


def _append(plane: object, requirement_id: str, evidence_kind: str) -> None:
    artifact_id = plane.artifacts.register(  # type: ignore[attr-defined]
        f"{requirement_id}:{evidence_kind}".encode(), critical_provenance()
    )
    plane.evidence.append(  # type: ignore[attr-defined]
        EvidenceInput(
            requirement_id=requirement_id,
            contract_id="C-16",
            artifact_id=artifact_id,
            test_id=evidence_kind,
            producer="independent-verification",
            result="PASS",
        )
    )


def test_complete_real_source_evidence_yields_only_capability_verdicts(
    plane: object,
) -> None:
    register = RequirementRegister.load(REPO)
    requirements = register.for_phase(PHASE)
    assert len(requirements) == 27

    with plane.session() as opened:  # type: ignore[attr-defined]
        # Ask the real applicability/Passport projection for its complete live
        # denominator, then satisfy exactly those register-owned obligations.
        _append(opened, requirements[0].req_id, requirements[0].required_evidence[0])
        seed = evidence_passport.build(
            evidence_graph.derive(opened.evidence, REPO), REPO, {}
        )
        for account in seed.capabilities:
            for requirement in account.requirements:
                for evidence_kind in requirement.required_evidence:
                    _append(opened, requirement.requirement_id, evidence_kind)
        passport = evidence_passport.build(
            evidence_graph.derive(opened.evidence, REPO), REPO, {}
        )

    assert passport.requirement_denominator == seed.requirement_denominator
    assert passport.completion_fraction == (
        passport.requirement_denominator,
        passport.requirement_denominator,
    )
    assert {
        requirement.req_id for requirement in requirements
    }.issubset({
        requirement.requirement_id
        for account in passport.capabilities
        for requirement in account.requirements
    })

    for account in passport.capabilities:
        verdict = evidence_passport.verdict(passport, account.capability, REPO)
        assert verdict.result == "VERIFIED"
        assert verdict.requirement_numerator == verdict.requirement_denominator
        assert verdict.missing_requirements == ()
        assert verdict.missing_evidence == ()

    # The result remains a capability evidence conclusion.  The Acceptance
    # Engine cannot smuggle in release, promotion, Stable mutation or a human
    # decision through its output model.
    verdict_fields = set(type(verdict).model_fields)
    assert verdict_fields.isdisjoint(
        {"phase_accepted", "release", "promoted", "stable", "human_gate_granted"}
    )


def test_machine_verdict_cannot_replace_a_required_human_gate(plane: object) -> None:
    requirement = RequirementRegister.load(REPO).get("ARK-REQ-0069")
    with plane.session() as opened:  # type: ignore[attr-defined]
        for evidence_kind in requirement.required_evidence:
            _append(opened, requirement.req_id, evidence_kind)
        passport = evidence_passport.build(
            evidence_graph.derive(opened.evidence, REPO), REPO, {}
        )

    gate = AcceptanceBoundaryPolicy.load(REPO).human_gates()[0]
    with pytest.raises(HumanGateNotRecorded, match=gate):
        evidence_passport.verdict(
            passport,
            requirement.owning_component,
            REPO,
            required_human_gate=gate,
        )
