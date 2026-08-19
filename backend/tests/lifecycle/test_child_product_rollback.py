"""C-36 child-product rollback (ARK-REQ-0132, ARK-REQ-0358). Stage A: real
rollback behaviour. Stage B: structural proofs it can never touch another
product or ARKALI's own Stable Core.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

import pytest
from pydantic import ValidationError

from arkali.kernel.contracts.content_address import address_of
from arkali.lifecycle.evolution.child_product_identity import (
    ChildProductIdentity,
    ChildProductMode,
)
from arkali.lifecycle.evolution.child_product_rollback import rollback_child_product
from arkali.lifecycle.evolution.child_product_version import (
    ChildProductVersion,
    ChildProductVersionLineage,
)
from arkali.lifecycle.evolution.errors import (
    ChildProductRollbackRequestInvalidError,
    UnknownVersionReferenceError,
)

MODULE: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parents[3]
    / "backend/arkali/lifecycle/evolution/child_product_rollback.py"
)
EVOLUTION_DIR: Final[pathlib.Path] = MODULE.parent


def content_ref(label: str) -> str:
    return address_of(label.encode("utf-8"))


def identity(**updates: object) -> ChildProductIdentity:
    values: dict[str, object] = {
        "product_id": "acme-task-tracker",
        "name": "Acme Task Tracker",
        "mode": ChildProductMode.AI_NATIVE_SELF_EVOLVING,
    }
    values.update(updates)
    return ChildProductIdentity.model_validate(values)


def two_version_lineage(subject: ChildProductIdentity) -> ChildProductVersionLineage:
    base = ChildProductVersionLineage(product_ref=subject.product_ref).append(
        ChildProductVersion(sequence=1, content_ref=content_ref("v1.4"), campaign_id="c-1")
    )
    return base.append(
        ChildProductVersion(
            sequence=2, content_ref=content_ref("v1.5"), campaign_id="c-2",
            parent_ref=base.current.version_ref,  # type: ignore[union-attr]
        )
    )


class TestRequestValidation:
    def test_mismatched_identity_and_lineage_is_refused(self) -> None:
        subject = identity(product_id="product-a")
        other_lineage = two_version_lineage(identity(product_id="product-b"))
        with pytest.raises(ChildProductRollbackRequestInvalidError):
            rollback_child_product(
                other_lineage, subject,
                target_version_ref=other_lineage.versions[0].version_ref,
                reason="revert bad change",
            )

    def test_empty_reason_is_refused(self) -> None:
        subject = identity()
        lineage = two_version_lineage(subject)
        with pytest.raises(ChildProductRollbackRequestInvalidError):
            rollback_child_product(
                lineage, subject,
                target_version_ref=lineage.versions[0].version_ref,
                reason="   ",
            )

    def test_unrecorded_target_is_refused(self) -> None:
        subject = identity()
        lineage = two_version_lineage(subject)
        with pytest.raises(UnknownVersionReferenceError):
            rollback_child_product(
                lineage, subject, target_version_ref="sha256:" + "f" * 64,
                reason="revert bad change",
            )


class TestRollbackNeverProducesNewContent:
    def test_restored_content_matches_the_target_exactly(self) -> None:
        subject = identity()
        lineage = two_version_lineage(subject)
        target = lineage.versions[0]
        rolled_back, receipt = rollback_child_product(
            lineage, subject, target_version_ref=target.version_ref,
            reason="v1.5 broke search",
        )
        assert rolled_back.current is not None
        assert rolled_back.current.content_ref == target.content_ref
        assert receipt.restored_content_ref == target.content_ref

    def test_history_is_preserved_never_truncated(self) -> None:
        subject = identity()
        lineage = two_version_lineage(subject)
        rolled_back, _ = rollback_child_product(
            lineage, subject, target_version_ref=lineage.versions[0].version_ref,
            reason="v1.5 broke search",
        )
        assert len(rolled_back.versions) == 3
        assert rolled_back.versions[0] == lineage.versions[0]
        assert rolled_back.versions[1] == lineage.versions[1]
        assert rolled_back.versions[2].is_rollback is True

    def test_the_original_lineage_is_unmutated(self) -> None:
        subject = identity()
        lineage = two_version_lineage(subject)
        original_count = len(lineage.versions)
        rollback_child_product(
            lineage, subject, target_version_ref=lineage.versions[0].version_ref,
            reason="v1.5 broke search",
        )
        assert len(lineage.versions) == original_count


class TestReceipt:
    def test_receipt_names_the_real_transition(self) -> None:
        subject = identity()
        lineage = two_version_lineage(subject)
        rolled_back, receipt = rollback_child_product(
            lineage, subject, target_version_ref=lineage.versions[0].version_ref,
            reason="v1.5 broke search",
        )
        assert receipt.product_ref == subject.product_ref
        assert receipt.from_version_ref == lineage.versions[1].version_ref
        assert receipt.to_version_ref == rolled_back.current.version_ref  # type: ignore[union-attr]
        assert receipt.reason == "v1.5 broke search"

    def test_receipt_ref_is_deterministic(self) -> None:
        subject = identity()
        lineage = two_version_lineage(subject)
        _, first = rollback_child_product(
            lineage, subject, target_version_ref=lineage.versions[0].version_ref,
            reason="v1.5 broke search",
        )
        _, second = rollback_child_product(
            lineage, subject, target_version_ref=lineage.versions[0].version_ref,
            reason="v1.5 broke search",
        )
        assert first.receipt_ref == second.receipt_ref

    def test_receipt_is_frozen(self) -> None:
        subject = identity()
        lineage = two_version_lineage(subject)
        _, receipt = rollback_child_product(
            lineage, subject, target_version_ref=lineage.versions[0].version_ref,
            reason="v1.5 broke search",
        )
        with pytest.raises(ValidationError):
            receipt.reason = "changed"  # type: ignore[misc]


class TestCrossProductIsolation:
    def test_rolling_back_one_product_never_touches_a_different_products_lineage(
        self,
    ) -> None:
        product_a = identity(product_id="product-a")
        product_b = identity(product_id="product-b")
        lineage_a = two_version_lineage(product_a)
        lineage_b = two_version_lineage(product_b)

        rolled_back_a, _ = rollback_child_product(
            lineage_a, product_a, target_version_ref=lineage_a.versions[0].version_ref,
            reason="revert",
        )

        assert lineage_b.versions == two_version_lineage(product_b).versions
        assert rolled_back_a.product_ref != lineage_b.product_ref


class TestNeverReachesArkaliStableCoreOrANewAuthority:
    """ADR-0009 reapplied at child-product scope: this module must never
    reach ARKALI's own Stable Core pointer or Recovery Supervisor, and no
    other `lifecycle.evolution` module may call `restore_to` outside its
    own definition."""

    def test_no_import_of_lifecycle_release_or_recovery(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "lifecycle.release" not in node.module
                assert "lifecycle.recovery" not in node.module

    def test_restore_to_is_called_only_here_and_in_the_lineage_owner(self) -> None:
        sole_caller = "child_product_rollback.py"
        lineage_owner = "child_product_version.py"
        offenders = []
        for path in sorted(EVOLUTION_DIR.glob("*.py")):
            if path.name in (sole_caller, lineage_owner, "__init__.py"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            called = {
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            }
            if "restore_to" in called:
                offenders.append(path.name)
        assert not offenders, f"unexpected restore_to call: {offenders}"
