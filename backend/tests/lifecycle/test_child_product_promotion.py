"""C-36 child-product promotion + scoped `HUMAN_GATE_3` grant (ARK-REQ-0132,
ARK-REQ-0358, ADR-0010). Mirrors `test_core_promotion_gate_scope.py`'s
exact fixture pattern - a temporary copy of the real `docs/` tree with only
`HUMAN_GATE_RECORDS.md` replaced. No accepted repository state is touched.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.rescoring_authorization import forbidden_issuers
from arkali.kernel.contracts.content_address import address_of
from arkali.lifecycle.evolution.child_product_identity import (
    ChildProductIdentity,
    ChildProductMode,
)
from arkali.lifecycle.evolution.child_product_promotion import (
    GATE_3,
    PROMOTE_CHILD_PRODUCT_OPERATION,
    ChildProductAcceptanceRecord,
    _child_promotion_revision_identity,
    _child_promotion_target_identity,
    authorize_child_product_promotion,
    promote_child_product,
)
from arkali.lifecycle.evolution.child_product_version import (
    ChildProductVersion,
    ChildProductVersionLineage,
)
from arkali.lifecycle.evolution.errors import (
    ChildProductAcceptanceRequiredError,
    ChildProductCandidateInvalidError,
    ChildProductPromotionNotAuthorizedError,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
RECORDS = "docs/acceptance/HUMAN_GATE_RECORDS.md"
OPERATION_HEADER = (
    "| ID | GATE | OPERATION | TARGET | REVISION | ISSUER | STATUS |\n"
    "|---|---|---|---|---|---|---|\n"
)


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


def acceptance(candidate_ref: str, *, exit_code: int = 0) -> ChildProductAcceptanceRecord:
    return ChildProductAcceptanceRecord(
        candidate_ref=candidate_ref, command="pytest child-product-suite",
        exit_code=exit_code,
    )


def operation_row(
    identifier: str, gate: str, operation: str, target: str, revision: str,
    issuer: str, status: str,
) -> str:
    return f"| {identifier} | {gate} | {operation} | {target} | {revision} | {issuer} | {status} |\n"


def repo_with_records(tmp_path: pathlib.Path, records_text: str) -> pathlib.Path:
    target = tmp_path / "repo"
    shutil.copytree(REPO / "docs", target / "docs")
    (target / RECORDS).write_text(records_text, encoding="utf-8")
    return target


@pytest.fixture()
def real_issuer() -> str:
    return "human operator"


@pytest.fixture()
def barred_issuer() -> str:
    barred = forbidden_issuers(REPO)
    assert barred, "AUTHORITY_MAP.yaml declares no prohibited actors; fixture has no subject"
    return next(iter(barred))


class TestChildProductAcceptanceRecord:
    def test_candidate_ref_must_be_a_real_content_address(self) -> None:
        with pytest.raises(ChildProductCandidateInvalidError):
            ChildProductAcceptanceRecord(
                candidate_ref="not-an-address", command="pytest", exit_code=0,
            )

    def test_command_must_be_named(self) -> None:
        with pytest.raises(ChildProductCandidateInvalidError):
            ChildProductAcceptanceRecord(
                candidate_ref=content_ref("v2"), command="   ", exit_code=0,
            )

    def test_passed_reflects_exit_code(self) -> None:
        assert acceptance(content_ref("v2")).passed is True
        assert acceptance(content_ref("v2"), exit_code=1).passed is False


class TestIdentityDerivation:
    def test_target_identity_is_deterministic(self) -> None:
        subject = identity()
        ref = content_ref("v2")
        assert _child_promotion_target_identity(
            subject, ref
        ) == _child_promotion_target_identity(subject, ref)

    def test_different_products_get_different_target_identity(self) -> None:
        ref = content_ref("v2")
        assert _child_promotion_target_identity(
            identity(product_id="a"), ref
        ) != _child_promotion_target_identity(identity(product_id="b"), ref)

    def test_different_candidates_get_different_target_identity(self) -> None:
        subject = identity()
        assert _child_promotion_target_identity(
            subject, content_ref("v2")
        ) != _child_promotion_target_identity(subject, content_ref("v3"))

    def test_revision_identity_changes_when_current_version_changes(self) -> None:
        ref = content_ref("v2")
        assert _child_promotion_revision_identity(
            None, ref
        ) != _child_promotion_revision_identity(content_ref("v1"), ref)

    def test_revision_identity_changes_when_candidate_changes(self) -> None:
        assert _child_promotion_revision_identity(
            content_ref("v1"), content_ref("v2")
        ) != _child_promotion_revision_identity(content_ref("v1"), content_ref("v3"))


class TestScopedGrantLookup:
    def test_no_grant_at_all_is_refused(self, tmp_path: pathlib.Path) -> None:
        repo = repo_with_records(tmp_path, OPERATION_HEADER)
        state = GovernanceState.load(repo)
        subject = identity()
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        context = authorize_child_product_promotion(
            state, subject, lineage, candidate_ref=content_ref("v2"),
        )
        assert context == {"human_gate_3_recorded": False}

    def test_an_exact_real_grant_is_honoured(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        subject = identity()
        candidate_ref = content_ref("v2")
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        target = _child_promotion_target_identity(subject, candidate_ref)
        revision = _child_promotion_revision_identity(None, candidate_ref)
        text = OPERATION_HEADER + operation_row(
            "PC3-1", GATE_3, PROMOTE_CHILD_PRODUCT_OPERATION, target, revision,
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_child_product_promotion(
            state, subject, lineage, candidate_ref=candidate_ref,
        )
        assert context == {"human_gate_3_recorded": True}

    def test_a_barred_actor_cannot_manufacture_its_own_grant(
        self, tmp_path: pathlib.Path, barred_issuer: str
    ) -> None:
        subject = identity()
        candidate_ref = content_ref("v2")
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        target = _child_promotion_target_identity(subject, candidate_ref)
        revision = _child_promotion_revision_identity(None, candidate_ref)
        text = OPERATION_HEADER + operation_row(
            "PC3-2", GATE_3, PROMOTE_CHILD_PRODUCT_OPERATION, target, revision,
            barred_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_child_product_promotion(
            state, subject, lineage, candidate_ref=candidate_ref,
        )
        assert context == {"human_gate_3_recorded": False}

    def test_a_grant_for_a_different_product_does_not_leak(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        product_a = identity(product_id="product-a")
        product_b = identity(product_id="product-b")
        candidate_ref = content_ref("v2")
        target_a = _child_promotion_target_identity(product_a, candidate_ref)
        revision = _child_promotion_revision_identity(None, candidate_ref)
        text = OPERATION_HEADER + operation_row(
            "PC3-3", GATE_3, PROMOTE_CHILD_PRODUCT_OPERATION, target_a, revision,
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        lineage_b = ChildProductVersionLineage(product_ref=product_b.product_ref)
        context = authorize_child_product_promotion(
            state, product_b, lineage_b, candidate_ref=candidate_ref,
        )
        assert context == {"human_gate_3_recorded": False}

    def test_a_grant_for_a_different_candidate_does_not_leak(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        subject = identity()
        granted_candidate = content_ref("v2")
        other_candidate = content_ref("v2-tampered")
        target = _child_promotion_target_identity(subject, granted_candidate)
        revision = _child_promotion_revision_identity(None, granted_candidate)
        text = OPERATION_HEADER + operation_row(
            "PC3-4", GATE_3, PROMOTE_CHILD_PRODUCT_OPERATION, target, revision,
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        context = authorize_child_product_promotion(
            state, subject, lineage, candidate_ref=other_candidate,
        )
        assert context == {"human_gate_3_recorded": False}

    def test_a_grant_for_a_different_gate_does_not_satisfy_gate_3(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        subject = identity()
        candidate_ref = content_ref("v2")
        target = _child_promotion_target_identity(subject, candidate_ref)
        revision = _child_promotion_revision_identity(None, candidate_ref)
        text = OPERATION_HEADER + operation_row(
            "PC3-5", "HUMAN_GATE_2", PROMOTE_CHILD_PRODUCT_OPERATION, target,
            revision, real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        context = authorize_child_product_promotion(
            state, subject, lineage, candidate_ref=candidate_ref,
        )
        assert context == {"human_gate_3_recorded": False}

    def test_a_stale_grant_does_not_authorize_after_the_current_version_moved(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        """Replay/downgrade defence: a grant computed against `current=None`
        (the genesis state) must not satisfy a lookup once a version has
        already been promoted and `current` has moved on."""
        subject = identity()
        candidate_ref = content_ref("v2")
        stale_target = _child_promotion_target_identity(subject, candidate_ref)
        stale_revision = _child_promotion_revision_identity(None, candidate_ref)
        text = OPERATION_HEADER + operation_row(
            "PC3-6", GATE_3, PROMOTE_CHILD_PRODUCT_OPERATION, stale_target,
            stale_revision, real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        already_promoted = ChildProductVersionLineage(
            product_ref=subject.product_ref,
        ).append(
            ChildProductVersion(
                sequence=1, content_ref=content_ref("v1"), campaign_id="c-0",
            )
        )
        context = authorize_child_product_promotion(
            state, subject, already_promoted, candidate_ref=candidate_ref,
        )
        assert context == {"human_gate_3_recorded": False}


class TestPromoteChildProductFullFlow:
    def test_malformed_candidate_is_refused_before_any_grant_lookup(
        self, tmp_path: pathlib.Path
    ) -> None:
        repo = repo_with_records(tmp_path, OPERATION_HEADER)
        state = GovernanceState.load(repo)
        subject = identity()
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        with pytest.raises(ChildProductCandidateInvalidError):
            promote_child_product(
                state, subject, lineage, candidate_ref="not-an-address",
                campaign_id="c-1", acceptance=acceptance("not-an-address"),
            )

    def test_non_sdk_eligible_mode_is_refused(self, tmp_path: pathlib.Path) -> None:
        repo = repo_with_records(tmp_path, OPERATION_HEADER)
        state = GovernanceState.load(repo)
        subject = identity(mode=ChildProductMode.STANDARD)
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        candidate_ref = content_ref("v2")
        with pytest.raises(ChildProductCandidateInvalidError):
            promote_child_product(
                state, subject, lineage, candidate_ref=candidate_ref,
                campaign_id="c-1", acceptance=acceptance(candidate_ref),
            )

    def test_acceptance_record_for_a_different_candidate_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        repo = repo_with_records(tmp_path, OPERATION_HEADER)
        state = GovernanceState.load(repo)
        subject = identity()
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        with pytest.raises(ChildProductAcceptanceRequiredError):
            promote_child_product(
                state, subject, lineage, candidate_ref=content_ref("v2"),
                campaign_id="c-1", acceptance=acceptance(content_ref("v2-other")),
            )

    def test_failed_acceptance_is_refused(self, tmp_path: pathlib.Path) -> None:
        repo = repo_with_records(tmp_path, OPERATION_HEADER)
        state = GovernanceState.load(repo)
        subject = identity()
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        candidate_ref = content_ref("v2")
        with pytest.raises(ChildProductAcceptanceRequiredError):
            promote_child_product(
                state, subject, lineage, candidate_ref=candidate_ref,
                campaign_id="c-1",
                acceptance=acceptance(candidate_ref, exit_code=1),
            )

    def test_no_grant_refuses_and_leaves_the_lineage_unmutated(
        self, tmp_path: pathlib.Path
    ) -> None:
        repo = repo_with_records(tmp_path, OPERATION_HEADER)
        state = GovernanceState.load(repo)
        subject = identity()
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        candidate_ref = content_ref("v2")
        with pytest.raises(ChildProductPromotionNotAuthorizedError):
            promote_child_product(
                state, subject, lineage, candidate_ref=candidate_ref,
                campaign_id="c-1", acceptance=acceptance(candidate_ref),
            )
        assert lineage.versions == ()

    def test_a_valid_grant_and_acceptance_promotes_the_candidate(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        subject = identity()
        candidate_ref = content_ref("v2")
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        target = _child_promotion_target_identity(subject, candidate_ref)
        revision = _child_promotion_revision_identity(None, candidate_ref)
        text = OPERATION_HEADER + operation_row(
            "PC3-7", GATE_3, PROMOTE_CHILD_PRODUCT_OPERATION, target, revision,
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)

        promoted = promote_child_product(
            state, subject, lineage, candidate_ref=candidate_ref,
            campaign_id="c-1", acceptance=acceptance(candidate_ref),
        )

        assert promoted.current is not None
        assert promoted.current.content_ref == candidate_ref
        assert promoted.current.is_rollback is False
        assert lineage.versions == ()  # the original is still unmutated

    def test_the_same_grant_does_not_authorize_a_second_promotion(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        """After a promotion, `current` has moved - the identical grant
        cannot be replayed to promote a second time, even for the exact
        same candidate content."""
        subject = identity()
        candidate_ref = content_ref("v2")
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref)
        target = _child_promotion_target_identity(subject, candidate_ref)
        revision = _child_promotion_revision_identity(None, candidate_ref)
        text = OPERATION_HEADER + operation_row(
            "PC3-8", GATE_3, PROMOTE_CHILD_PRODUCT_OPERATION, target, revision,
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)

        promoted = promote_child_product(
            state, subject, lineage, candidate_ref=candidate_ref,
            campaign_id="c-1", acceptance=acceptance(candidate_ref),
        )
        with pytest.raises(ChildProductPromotionNotAuthorizedError):
            promote_child_product(
                state, subject, promoted, candidate_ref=candidate_ref,
                campaign_id="c-2", acceptance=acceptance(candidate_ref),
            )
