from __future__ import annotations

import pathlib

import pytest

from arkali.engineering.candidate.campaign_budget import (
    CampaignBudget,
    CampaignBudgetExhaustedError,
    CampaignEscalatedError,
    CANDIDATE_DEFECT,
    CAMPAIGN_BUDGET_EXHAUSTED,
    CAMPAIGN_ESCALATED,
    CAMPAIGN_RUNNING,
    fingerprint_of,
    GenerationCampaignLedger,
    MODEL_VARIANCE,
)

_STAGE_FAILURE_MESSAGE = (
    "[ARK-ERR-0116] stage 'frontend_forms' exhausted 4 attempts: "
    "frontend_ui_missing_edit_ui:frontend/src/:product_ux_spec declares an edit "
    "action but the frontend never references an update/edit-named client "
    "function anywhere"
)


class TestFingerprinting:
    def test_a_stage_failure_fingerprint_names_the_stage_and_finding(self) -> None:
        """golden-work-124's own real error message."""
        fp = fingerprint_of("STAGE_FAILED", _STAGE_FAILURE_MESSAGE)
        assert fp == "STAGE_FAILED:frontend_forms:frontend_ui_missing_edit_ui"

    def test_an_unrecognized_message_shape_still_gets_a_fingerprint(self) -> None:
        fp = fingerprint_of("ACCEPTANCE_FAILED", "npm install failed: ECONNRESET")
        assert fp == "ACCEPTANCE_FAILED:npm install failed: ECONNRESET"

    def test_two_different_stages_never_share_a_fingerprint(self) -> None:
        a = fingerprint_of(
            "STAGE_FAILED",
            "stage 'frontend_forms' exhausted 4 attempts: frontend_ui_missing_edit_ui:x",
        )
        b = fingerprint_of(
            "STAGE_FAILED",
            "stage 'backend_contract' exhausted 4 attempts: missing_local_module:x",
        )
        assert a != b


class TestCampaignBudgetLimits:
    def test_a_campaign_may_start_new_candidates_while_under_budget(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = GenerationCampaignLedger.load_or_create(tmp_path, "camp-a", CampaignBudget())
        assert ledger.status() == CAMPAIGN_RUNNING
        ledger.refuse_new_candidate_unless_permitted(override_confirmed=False)  # must not raise

    def test_exhausting_the_candidate_count_budget_refuses_without_override(
        self, tmp_path: pathlib.Path,
    ) -> None:
        budget = CampaignBudget(max_new_candidates=1, max_total_seconds=10_000)
        ledger = GenerationCampaignLedger.load_or_create(tmp_path, "camp-b", budget)
        ledger.record("golden-work-1", "STAGED_GENERATION_PASS", elapsed_seconds=10)
        assert ledger.status() == CAMPAIGN_BUDGET_EXHAUSTED
        with pytest.raises(CampaignBudgetExhaustedError):
            ledger.refuse_new_candidate_unless_permitted(override_confirmed=False)

    def test_a_confirmed_override_permits_one_more_candidate_past_budget(
        self, tmp_path: pathlib.Path,
    ) -> None:
        budget = CampaignBudget(max_new_candidates=1, max_total_seconds=10_000)
        ledger = GenerationCampaignLedger.load_or_create(tmp_path, "camp-c", budget)
        ledger.record("golden-work-1", "STAGED_GENERATION_PASS", elapsed_seconds=10)
        ledger.refuse_new_candidate_unless_permitted(override_confirmed=True)  # must not raise

    def test_exhausting_the_time_budget_refuses_without_override(
        self, tmp_path: pathlib.Path,
    ) -> None:
        budget = CampaignBudget(max_new_candidates=99, max_total_seconds=100)
        ledger = GenerationCampaignLedger.load_or_create(tmp_path, "camp-d", budget)
        ledger.record("golden-work-1", "STAGE_FAILED", elapsed_seconds=150)
        assert ledger.status() == CAMPAIGN_BUDGET_EXHAUSTED
        with pytest.raises(CampaignBudgetExhaustedError):
            ledger.refuse_new_candidate_unless_permitted(override_confirmed=False)


class TestFingerprintEscalation:
    def test_a_fingerprint_recurring_up_to_the_limit_does_not_escalate(
        self, tmp_path: pathlib.Path,
    ) -> None:
        budget = CampaignBudget(max_same_fingerprint_repeats=2, max_new_candidates=99)
        ledger = GenerationCampaignLedger.load_or_create(tmp_path, "camp-e", budget)
        for candidate in ("golden-work-1", "golden-work-2"):
            ledger.record(
                candidate, "STAGE_FAILED", elapsed_seconds=10,
                failure_class=CANDIDATE_DEFECT, error_message=_STAGE_FAILURE_MESSAGE,
            )
        assert ledger.status() == CAMPAIGN_RUNNING
        ledger.refuse_new_candidate_unless_permitted(override_confirmed=False)

    def test_a_third_recurrence_of_the_same_fingerprint_escalates(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """"Aynı fingerprint üçüncü kez çıkarsa yeni aday başlatma" -- the
        3rd occurrence of the same root cause stops the campaign outright."""
        budget = CampaignBudget(max_same_fingerprint_repeats=2, max_new_candidates=99)
        ledger = GenerationCampaignLedger.load_or_create(tmp_path, "camp-f", budget)
        for candidate in ("golden-work-1", "golden-work-2", "golden-work-3"):
            ledger.record(
                candidate, "STAGE_FAILED", elapsed_seconds=10,
                failure_class=CANDIDATE_DEFECT, error_message=_STAGE_FAILURE_MESSAGE,
            )
        assert ledger.status() == CAMPAIGN_ESCALATED

    def test_escalation_refuses_even_with_a_confirmed_override(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """A recurring root cause needs human review, not a bigger budget --
        override never bypasses CAMPAIGN_ESCALATED."""
        budget = CampaignBudget(max_same_fingerprint_repeats=2, max_new_candidates=99)
        ledger = GenerationCampaignLedger.load_or_create(tmp_path, "camp-g", budget)
        for candidate in ("golden-work-1", "golden-work-2", "golden-work-3"):
            ledger.record(
                candidate, "STAGE_FAILED", elapsed_seconds=10,
                failure_class=CANDIDATE_DEFECT, error_message=_STAGE_FAILURE_MESSAGE,
            )
        with pytest.raises(CampaignEscalatedError):
            ledger.refuse_new_candidate_unless_permitted(override_confirmed=True)

    def test_different_fingerprints_do_not_accumulate_toward_escalation(
        self, tmp_path: pathlib.Path,
    ) -> None:
        budget = CampaignBudget(max_same_fingerprint_repeats=2, max_new_candidates=99)
        ledger = GenerationCampaignLedger.load_or_create(tmp_path, "camp-h", budget)
        ledger.record(
            "golden-work-1", "STAGE_FAILED", elapsed_seconds=10,
            failure_class=MODEL_VARIANCE,
            error_message="stage 'frontend_forms' exhausted 4 attempts: finding_a:x",
        )
        ledger.record(
            "golden-work-2", "STAGE_FAILED", elapsed_seconds=10,
            failure_class=MODEL_VARIANCE,
            error_message="stage 'backend_contract' exhausted 4 attempts: finding_b:x",
        )
        ledger.record(
            "golden-work-3", "STAGE_FAILED", elapsed_seconds=10,
            failure_class=MODEL_VARIANCE,
            error_message="stage 'frontend_ui' exhausted 4 attempts: finding_c:x",
        )
        assert ledger.status() == CAMPAIGN_RUNNING


class TestBudgetPersistenceAcrossSessions:
    def test_reloading_a_campaign_preserves_its_consumption(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """A new Claude session (a fresh process re-reading the same
        campaign_id) must see exactly what was already consumed -- the
        budget is never silently reset just because the process restarted."""
        budget = CampaignBudget(max_new_candidates=5)
        first = GenerationCampaignLedger.load_or_create(tmp_path, "camp-i", budget)
        first.record("golden-work-1", "STAGE_FAILED", elapsed_seconds=10, failure_class=CANDIDATE_DEFECT)
        first.record("golden-work-2", "STAGE_FAILED", elapsed_seconds=10, failure_class=CANDIDATE_DEFECT)

        reloaded = GenerationCampaignLedger.load_or_create(
            tmp_path, "camp-i", CampaignBudget(max_new_candidates=5),
        )
        assert reloaded.consumed_candidates == 2

    def test_reloading_a_campaign_ignores_a_different_default_budget(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """The originally declared budget wins on reload -- a caller cannot
        quietly loosen it by passing a bigger default on the next run."""
        original = GenerationCampaignLedger.load_or_create(
            tmp_path, "camp-j", CampaignBudget(max_new_candidates=1),
        )
        original.record("golden-work-1", "STAGED_GENERATION_PASS", elapsed_seconds=1)
        assert original.status() == CAMPAIGN_BUDGET_EXHAUSTED

        reloaded = GenerationCampaignLedger.load_or_create(
            tmp_path, "camp-j", CampaignBudget(max_new_candidates=100),
        )
        assert reloaded.budget.max_new_candidates == 1
        assert reloaded.status() == CAMPAIGN_BUDGET_EXHAUSTED
