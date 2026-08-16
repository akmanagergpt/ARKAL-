from __future__ import annotations

import pytest
from pydantic import ValidationError

from arkali.engineering.knowledge.contracts import (
    EvidenceKind,
    EvidenceReference,
    KnowledgeRecord,
    KnowledgeValidityState,
    SelfReportedClaim,
    assert_transition_allowed,
)
from arkali.engineering.knowledge.errors import (
    IllegalValidityTransitionError,
    UnbackedKnowledgeClaimError,
)
from arkali.kernel.contracts.content_address import address_of, is_address

REAL_ADDRESS = address_of(b"phase-18-evidence")


def evidence(**updates: object) -> EvidenceReference:
    values: dict[str, object] = {
        "kind": EvidenceKind.ACCEPTANCE_RESULT,
        "content_address": REAL_ADDRESS,
    }
    values.update(updates)
    return EvidenceReference.model_validate(values)


def record(**updates: object) -> KnowledgeRecord:
    values: dict[str, object] = {
        "subject": "repair-strategy: minimal-contract-repair",
        "claim": "resolves ContractViolation for mismatched pydantic fields",
        "evidence": evidence(),
    }
    values.update(updates)
    return KnowledgeRecord.model_validate(values)


class TestEvidenceReferenceIsRealAndStructural:
    def test_a_canonical_content_address_is_accepted(self) -> None:
        ref = evidence()
        assert is_address(ref.content_address)

    def test_a_malformed_content_address_is_refused(self) -> None:
        with pytest.raises(UnbackedKnowledgeClaimError):
            evidence(content_address="not-a-real-address")

    def test_evidence_kind_is_a_closed_real_evidence_vocabulary(self) -> None:
        assert {member.value for member in EvidenceKind} == {
            "artifact",
            "audit",
            "acceptance_result",
        }

    def test_self_reported_claim_cannot_substitute_for_evidence(self) -> None:
        """ARK-REQ-0126: only evidence-backed outcomes become authoritative
        knowledge — enforced by type, not by inspecting prose."""
        with pytest.raises(ValidationError):
            KnowledgeRecord(
                subject="s",
                claim="c",
                evidence=SelfReportedClaim(  # type: ignore[arg-type]
                    reported_by="model-x", claim="I performed flawlessly"
                ),
            )

    def test_evidence_is_required_not_optional(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeRecord(subject="s", claim="c")  # type: ignore[call-arg]


class TestKnowledgeRecordIdentityAndImmutability:
    def test_record_ref_is_deterministic_and_content_addressed(self) -> None:
        first = record()
        second = record()
        assert first.record_ref == second.record_ref
        assert is_address(first.record_ref)

    def test_record_defaults_to_fresh(self) -> None:
        assert record().validity_state is KnowledgeValidityState.FRESH

    def test_record_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            record().claim = "changed"  # type: ignore[misc]


class TestValidityLifecycleTransitions:
    """ARK-REQ-0127: knowledge lifecycle states, structurally enforced."""

    @pytest.mark.parametrize(
        ("current", "target"),
        (
            (KnowledgeValidityState.FRESH, KnowledgeValidityState.AGING),
            (KnowledgeValidityState.FRESH, KnowledgeValidityState.INVALID),
            (KnowledgeValidityState.AGING, KnowledgeValidityState.FRESH),
            (KnowledgeValidityState.AGING, KnowledgeValidityState.REVALIDATION_REQUIRED),
            (KnowledgeValidityState.AGING, KnowledgeValidityState.INVALID),
            (
                KnowledgeValidityState.REVALIDATION_REQUIRED,
                KnowledgeValidityState.FRESH,
            ),
            (
                KnowledgeValidityState.REVALIDATION_REQUIRED,
                KnowledgeValidityState.DEPRECATED,
            ),
            (
                KnowledgeValidityState.REVALIDATION_REQUIRED,
                KnowledgeValidityState.INVALID,
            ),
            (KnowledgeValidityState.DEPRECATED, KnowledgeValidityState.INVALID),
        ),
    )
    def test_every_declared_transition_is_permitted(
        self, current: KnowledgeValidityState, target: KnowledgeValidityState
    ) -> None:
        assert_transition_allowed(current, target)
        moved = record(validity_state=current).transitioned(target)
        assert moved.validity_state is target

    @pytest.mark.parametrize(
        ("current", "target"),
        (
            (KnowledgeValidityState.FRESH, KnowledgeValidityState.DEPRECATED),
            (
                KnowledgeValidityState.FRESH,
                KnowledgeValidityState.REVALIDATION_REQUIRED,
            ),
            (KnowledgeValidityState.DEPRECATED, KnowledgeValidityState.FRESH),
            (KnowledgeValidityState.DEPRECATED, KnowledgeValidityState.AGING),
            (KnowledgeValidityState.INVALID, KnowledgeValidityState.FRESH),
            (KnowledgeValidityState.INVALID, KnowledgeValidityState.AGING),
        ),
    )
    def test_every_undeclared_transition_is_refused(
        self, current: KnowledgeValidityState, target: KnowledgeValidityState
    ) -> None:
        with pytest.raises(IllegalValidityTransitionError):
            assert_transition_allowed(current, target)
        with pytest.raises(IllegalValidityTransitionError):
            record(validity_state=current).transitioned(target)

    def test_invalid_is_genuinely_terminal(self) -> None:
        for target in KnowledgeValidityState:
            with pytest.raises(IllegalValidityTransitionError):
                assert_transition_allowed(KnowledgeValidityState.INVALID, target)

    def test_transitioned_returns_a_new_record_and_preserves_the_original(self) -> None:
        original = record()
        moved = original.transitioned(KnowledgeValidityState.AGING)
        assert original.validity_state is KnowledgeValidityState.FRESH
        assert moved.validity_state is KnowledgeValidityState.AGING
        assert moved.record_ref != original.record_ref
