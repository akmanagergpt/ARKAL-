from __future__ import annotations

import pytest
from pydantic import ValidationError

from arkali.engineering.knowledge.component_metadata import (
    CompatibilityMetadata,
    ComponentTestMetadata,
    ReusableComponentDescriptor,
    SecurityMetadata,
)
from arkali.engineering.knowledge.errors import IncompleteComponentMetadataError
from arkali.kernel.contracts.content_address import address_of, is_address

SUITE_REF = address_of(b"phase-18-test-suite")
REVIEW_REF = address_of(b"phase-18-security-review")


def descriptor(**updates: object) -> ReusableComponentDescriptor:
    values: dict[str, object] = {
        "component_id": "workflow-retry-node",
        "test": ComponentTestMetadata(suite_ref=SUITE_REF, passed=42, failed=0),
        "security": SecurityMetadata(review_ref=REVIEW_REF, findings_cleared=True),
        "compatibility": CompatibilityMetadata(
            contract_version="1.0.0", compatible_with=("execution.workflow",)
        ),
    }
    values.update(updates)
    return ReusableComponentDescriptor.model_validate(values)


class TestAllThreeMetadataCategoriesAreMandatory:
    """ARK-REQ-0128: reusable components carry test/security/compatibility
    metadata — refused at construction, not silently defaulted."""

    def test_the_three_canonical_categories_are_required_fields(self) -> None:
        assert set(ReusableComponentDescriptor.model_fields) >= {
            "test",
            "security",
            "compatibility",
        }

    @pytest.mark.parametrize("missing_field", ("test", "security", "compatibility"))
    def test_a_descriptor_missing_any_category_is_refused(
        self, missing_field: str
    ) -> None:
        full = {
            "component_id": "comp",
            "test": ComponentTestMetadata(suite_ref=SUITE_REF, passed=1, failed=0),
            "security": SecurityMetadata(review_ref=REVIEW_REF, findings_cleared=True),
            "compatibility": CompatibilityMetadata(
                contract_version="1.0.0", compatible_with=("engineering.agent",)
            ),
        }
        del full[missing_field]
        with pytest.raises(ValidationError):
            ReusableComponentDescriptor.model_validate(full)

    def test_compatibility_metadata_requires_at_least_one_target(self) -> None:
        with pytest.raises(IncompleteComponentMetadataError):
            CompatibilityMetadata(contract_version="1.0.0", compatible_with=())


class TestVerifiedReusableIsDerivedAndHonest:
    def test_clean_metadata_is_verified_reusable(self) -> None:
        assert descriptor().is_verified_reusable is True

    def test_a_failing_test_is_carried_but_not_verified_reusable(self) -> None:
        component = descriptor(
            test=ComponentTestMetadata(suite_ref=SUITE_REF, passed=41, failed=1)
        )
        assert component.test.failed == 1  # metadata is not hidden
        assert component.is_verified_reusable is False

    def test_an_open_security_finding_is_carried_but_not_verified_reusable(self) -> None:
        component = descriptor(
            security=SecurityMetadata(review_ref=REVIEW_REF, findings_cleared=False)
        )
        assert component.security.findings_cleared is False
        assert component.is_verified_reusable is False


class TestDescriptorIdentity:
    def test_descriptor_ref_is_deterministic_and_content_addressed(self) -> None:
        first = descriptor()
        second = descriptor()
        assert first.descriptor_ref == second.descriptor_ref
        assert is_address(first.descriptor_ref)

    def test_a_different_component_has_a_different_ref(self) -> None:
        assert descriptor().descriptor_ref != descriptor(
            component_id="a-different-component"
        ).descriptor_ref

    def test_descriptor_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            descriptor().component_id = "changed"  # type: ignore[misc]
