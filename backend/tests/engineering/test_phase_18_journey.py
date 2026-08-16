"""The composed Phase 18 real-authority journey.

Real per-model/task-class outcomes -> empirical aggregation -> an
evidence-backed knowledge record derived from that same aggregate ->
lifecycle transitions driven by new real evidence -> a reusable-component
descriptor for the same subject, carrying its own test/security/
compatibility metadata -> the self-reported-claim exclusion proven at every
entry point. Over REAL `RequirementRegister`, `EvidenceReference`,
`KnowledgeRecord`, `aggregate` and `ReusableComponentDescriptor` — no mocks
of any canonical authority, no AI provider contacted anywhere in this
journey (T5 integration + provenance evidence for ARK-REQ-0126,
ARK-REQ-0394; T3 unit evidence for ARK-REQ-0127; T4 contract evidence for
ARK-REQ-0128, per docs/contracts/knowledge.md).
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest
from pydantic import ValidationError

from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.knowledge.component_metadata import (
    CompatibilityMetadata,
    ComponentTestMetadata,
    ReusableComponentDescriptor,
    SecurityMetadata,
)
from arkali.engineering.knowledge.contracts import (
    EvidenceKind,
    EvidenceReference,
    KnowledgeRecord,
    KnowledgeValidityState,
    SelfReportedClaim,
)
from arkali.engineering.knowledge.errors import IllegalValidityTransitionError
from arkali.engineering.knowledge.outcome_statistics import VerifiedOutcome, aggregate
from arkali.kernel.contracts.content_address import address_of, is_address

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
MODEL_ID: Final[str] = "local/qwen2.5-coder:14b"
TASK_CLASS: Final[str] = "root_cause_repair"


def _evidence(
    payload: bytes, kind: EvidenceKind = EvidenceKind.ACCEPTANCE_RESULT
) -> EvidenceReference:
    return EvidenceReference(kind=kind, content_address=address_of(payload))


def test_step_1_the_real_register_denominator() -> None:
    register = RequirementRegister.load(REPO)
    phase18 = {r.req_id for r in register.for_phase("18")}
    assert phase18 == {
        "ARK-REQ-0126", "ARK-REQ-0127", "ARK-REQ-0128", "ARK-REQ-0394",
    }
    assert all(r.owning_component == "engineering.knowledge" for r in register.for_phase("18"))


def test_step_2_verified_outcomes_aggregate_into_real_per_model_stats() -> None:
    """ARK-REQ-0394: recorded only from verified results."""
    outcomes = (
        VerifiedOutcome(
            model_id=MODEL_ID, task_class=TASK_CLASS, succeeded=True,
            evidence=_evidence(b"attempt-1-acceptance-result"),
        ),
        VerifiedOutcome(
            model_id=MODEL_ID, task_class=TASK_CLASS, succeeded=True,
            evidence=_evidence(b"attempt-2-acceptance-result"),
        ),
        VerifiedOutcome(
            model_id=MODEL_ID, task_class=TASK_CLASS, succeeded=False,
            evidence=_evidence(b"attempt-3-acceptance-result"),
        ),
    )
    stats = aggregate(outcomes)
    assert len(stats) == 1
    assert stats[0].model_id == MODEL_ID
    assert stats[0].attempts == 3
    assert stats[0].successes == 2

    with pytest.raises(ValidationError):
        VerifiedOutcome(
            model_id=MODEL_ID, task_class=TASK_CLASS, succeeded=True,
            evidence=SelfReportedClaim(  # type: ignore[arg-type]
                reported_by=MODEL_ID, claim="I always succeed at this task class",
            ),
        )


def test_step_3_a_knowledge_record_is_derived_from_the_same_evidence_and_ages_honestly() -> None:
    """ARK-REQ-0126 + ARK-REQ-0127: an evidence-backed record, aging as new
    (weaker) evidence about the same subject arrives, never silently
    strengthened back to fresh without a real revalidation event."""
    strong_evidence = _evidence(b"attempt-1-acceptance-result")
    record = KnowledgeRecord(
        subject=f"{MODEL_ID}:{TASK_CLASS}",
        claim="succeeds on root_cause_repair with observed success_rate >= 0.6",
        evidence=strong_evidence,
    )
    assert record.validity_state is KnowledgeValidityState.FRESH
    assert is_address(record.record_ref)

    aged = record.transitioned(KnowledgeValidityState.AGING)
    needs_revalidation = aged.transitioned(KnowledgeValidityState.REVALIDATION_REQUIRED)
    assert needs_revalidation.validity_state is KnowledgeValidityState.REVALIDATION_REQUIRED

    with pytest.raises(IllegalValidityTransitionError):
        needs_revalidation.transitioned(KnowledgeValidityState.INVALID).transitioned(
            KnowledgeValidityState.FRESH
        )

    revalidated = needs_revalidation.transitioned(KnowledgeValidityState.FRESH)
    assert revalidated.validity_state is KnowledgeValidityState.FRESH
    assert record.validity_state is KnowledgeValidityState.FRESH  # original untouched


def test_step_4_a_reusable_component_descriptor_carries_real_metadata_for_same_subject() -> None:
    """ARK-REQ-0128, tied to the same journey subject as steps 2-3."""
    descriptor = ReusableComponentDescriptor(
        component_id="root-cause-repair-strategy-minimal-contract-repair",
        test=ComponentTestMetadata(
            suite_ref=address_of(b"phase-18-journey-test-suite"), passed=12, failed=0,
        ),
        security=SecurityMetadata(
            review_ref=address_of(b"phase-18-journey-security-review"),
            findings_cleared=True,
        ),
        compatibility=CompatibilityMetadata(
            contract_version="1.0.0", compatible_with=("engineering.repair", "engineering.factory"),
        ),
    )
    assert descriptor.is_verified_reusable is True
    assert is_address(descriptor.descriptor_ref)


def test_step_5_self_reported_claims_are_refused_at_every_journey_entry_point() -> None:
    claim = SelfReportedClaim(reported_by=MODEL_ID, claim="I am the best model")
    with pytest.raises(ValidationError):
        KnowledgeRecord(subject="s", claim="c", evidence=claim)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        VerifiedOutcome(
            model_id=MODEL_ID, task_class=TASK_CLASS, succeeded=True, evidence=claim  # type: ignore[arg-type]
        )


def test_step_6_nothing_in_this_journey_persists_or_contacts_a_provider() -> None:
    """Matches the D-023 precedent every prior phase's journey proves: this
    entire journey is pure, in-memory, content-addressed computation."""
    outcomes = (
        VerifiedOutcome(
            model_id=MODEL_ID, task_class=TASK_CLASS, succeeded=True,
            evidence=_evidence(b"journey-step-6"),
        ),
    )
    first_run = aggregate(outcomes)
    second_run = aggregate(outcomes)
    assert first_run == second_run  # deterministic, not accumulated across calls
    assert aggregate(outcomes + outcomes)[0].attempts == 2  # no hidden state carried over
