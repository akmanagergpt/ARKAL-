"""Read-only Phase 30 production-history HTTP surface: real backend, real
SQLite, real PDP, real `CandidateLedger`/`GenerationCampaignLedger` on
disk - the same Level 3 real-collaborator posture
`test_command_operations_api.py` already establishes for its own route.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.engineering.candidate.campaign_budget import CampaignBudget, GenerationCampaignLedger
from arkali.engineering.candidate.ledger import CandidateLedger, GENERATING, GenerationProvenance, hash_text
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.surfaces.command.app import _CommandExtensions, create_app

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"


def alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "factory_history.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def var_root(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "var"


def _candidate_history_source(var_root: pathlib.Path):  # noqa: ANN201
    """Mirrors `run_command_center.py::_factory_candidate_history`
    exactly, over an isolated root."""
    from arkali.surfaces.command.factory_history import FactoryCandidateSummary

    ledger = CandidateLedger(var_root / "factory" / "candidates" / "_ledger")

    def read() -> tuple[FactoryCandidateSummary, ...]:
        return tuple(
            FactoryCandidateSummary(
                candidate_id=candidate_id,
                state=ledger.classify(candidate_id),
                recorded_at=str((ledger.latest(candidate_id) or {}).get("recorded_at", "")),
            )
            for candidate_id in ledger.all_candidate_ids()
        )

    return read, ledger


def _campaign_history_source(var_root: pathlib.Path):  # noqa: ANN201
    """Mirrors `run_command_center.py::_factory_campaign_history` exactly,
    over an isolated root."""
    from arkali.engineering.candidate.campaign_budget import list_campaign_ids
    from arkali.surfaces.command.factory_history import FactoryCampaignAttempt, FactoryCampaignSummary

    campaigns_root = var_root / "factory" / "campaigns"

    def read() -> tuple[FactoryCampaignSummary, ...]:
        summaries = []
        for campaign_id in list_campaign_ids(campaigns_root):
            campaign = GenerationCampaignLedger.load_or_create(
                campaigns_root, campaign_id, CampaignBudget(),
            )
            summaries.append(FactoryCampaignSummary(
                campaign_id=campaign_id,
                max_new_candidates=campaign.budget.max_new_candidates,
                max_total_seconds=campaign.budget.max_total_seconds,
                max_same_fingerprint_repeats=campaign.budget.max_same_fingerprint_repeats,
                consumed_candidates=campaign.consumed_candidates,
                consumed_seconds=campaign.consumed_seconds,
                status=campaign.status(),
                attempts=tuple(
                    FactoryCampaignAttempt(
                        candidate_id=str(a["candidate_id"]),
                        outcome=str(a["outcome"]),
                        failure_class=a.get("failure_class"),
                        fingerprint=a.get("fingerprint"),
                        elapsed_seconds=float(a["elapsed_seconds"]),
                        recorded_at=str(a["recorded_at"]),
                    )
                    for a in campaign.attempts()
                ),
            ))
        return tuple(summaries)

    return read


@pytest.fixture()
def app(engine: Engine, pdp: PolicyDecisionPoint, var_root: pathlib.Path) -> FastAPI:
    candidate_read, _ledger = _candidate_history_source(var_root)
    return create_app(engine, pdp, extensions=_CommandExtensions(
        factory_candidate_history=candidate_read,
        factory_campaign_history=_campaign_history_source(var_root),
    ))


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as opened:
        yield opened


def _provenance() -> GenerationProvenance:
    return GenerationProvenance(
        goal_hash=hash_text("goal"), source_commit="abc", runtime="ollama",
        endpoint="local", model="qwen",
    )


class TestFactoryHistoryIsRealNotFabricated:
    def test_an_empty_host_reports_empty_history_not_fabricated_rows(
        self, client: TestClient,
    ) -> None:
        response = client.get("/api/factory/history")
        assert response.status_code == 200
        assert response.json() == {"candidates": [], "campaigns": []}

    def test_a_real_candidate_and_campaign_are_reflected_live(
        self, client: TestClient, var_root: pathlib.Path,
    ) -> None:
        candidates_root = var_root / "factory" / "candidates"
        work = candidates_root / "golden-work-test"
        ledger = CandidateLedger(candidates_root / "_ledger")
        ledger.allocate("golden-work-test", provenance=_provenance())
        ledger.record_state("golden-work-test", GENERATING, work)

        campaign = GenerationCampaignLedger.load_or_create(
            var_root / "factory" / "campaigns", "test-campaign", CampaignBudget(max_new_candidates=1),
        )
        campaign.record(
            "golden-work-test", "STAGE_FAILED", elapsed_seconds=12.5,
            failure_class="candidate_defect", error_message="stage 'x' exhausted 4 attempts: y",
        )

        body = client.get("/api/factory/history").json()
        assert body["candidates"] == [
            {"candidate_id": "golden-work-test", "state": "GENERATING", "recorded_at": body["candidates"][0]["recorded_at"]},
        ]
        assert len(body["campaigns"]) == 1
        campaign_body = body["campaigns"][0]
        assert campaign_body["campaign_id"] == "test-campaign"
        assert campaign_body["max_new_candidates"] == 1
        assert campaign_body["consumed_candidates"] == 1
        assert len(campaign_body["attempts"]) == 1
        assert campaign_body["attempts"][0]["outcome"] == "STAGE_FAILED"
        assert campaign_body["attempts"][0]["failure_class"] == "candidate_defect"

    def test_without_factory_history_wiring_the_route_does_not_exist(
        self, engine: Engine, pdp: PolicyDecisionPoint,
    ) -> None:
        plain_app = create_app(engine, pdp)
        with TestClient(plain_app) as plain_client:
            response = plain_client.get("/api/factory/history")
        assert response.status_code == 404

    def test_the_route_is_never_a_trigger(self, client: TestClient) -> None:
        """A real regression control: this surface never accepts a POST."""
        response = client.post("/api/factory/history", json={})
        assert response.status_code in (404, 405)
