"""C-36 child-product identity + the three canonical modes (ARK-REQ-0131)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arkali.lifecycle.evolution.child_product_identity import (
    ChildProductIdentity,
    ChildProductMode,
)


def identity(**updates: object) -> ChildProductIdentity:
    values: dict[str, object] = {
        "product_id": "acme-task-tracker",
        "name": "Acme Task Tracker",
        "mode": ChildProductMode.AI_NATIVE_SELF_EVOLVING,
    }
    values.update(updates)
    return ChildProductIdentity.model_validate(values)


class TestChildProductMode:
    def test_exactly_three_canonical_modes_exist(self) -> None:
        """MS 'AI-Native Child Products' names exactly three modes."""
        assert {m.value for m in ChildProductMode} == {
            "STANDARD", "AI_ASSISTED", "AI_NATIVE_SELF_EVOLVING",
        }

    def test_a_fourth_mode_cannot_be_constructed(self) -> None:
        with pytest.raises(ValueError):
            ChildProductMode("PROFESSIONAL")


class TestChildProductIdentity:
    def test_frozen_and_extra_forbidden(self) -> None:
        subject = identity()
        with pytest.raises(ValidationError):
            subject.name = "renamed"  # type: ignore[misc]
        with pytest.raises(ValidationError):
            ChildProductIdentity.model_validate(
                {**subject.model_dump(), "extra_field": 1}
            )

    def test_only_ai_native_self_evolving_uses_the_sdk(self) -> None:
        assert identity(mode=ChildProductMode.STANDARD).uses_evolution_sdk is False
        assert identity(mode=ChildProductMode.AI_ASSISTED).uses_evolution_sdk is False
        assert (
            identity(mode=ChildProductMode.AI_NATIVE_SELF_EVOLVING).uses_evolution_sdk
            is True
        )

    def test_product_ref_is_deterministic_and_content_addressed(self) -> None:
        first = identity()
        second = identity()
        assert first.product_ref == second.product_ref
        assert first.product_ref.startswith("sha256:")

    def test_product_ref_changes_with_declared_content(self) -> None:
        assert identity().product_ref != identity(name="Different Name").product_ref
        assert (
            identity().product_ref
            != identity(mode=ChildProductMode.STANDARD).product_ref
        )

    def test_empty_product_id_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            identity(product_id="")
