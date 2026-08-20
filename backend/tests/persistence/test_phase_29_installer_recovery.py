"""Phase 29 integration reuses, and never shadows, C-32."""

from __future__ import annotations

import ast
import pathlib
import sys
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy.engine import Engine

from alembic import command
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.audit.chain import AuditChain
from arkali.kernel.contracts.content_address import address_of
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.release.stable_path import StableCandidatePath
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
sys.path.insert(0, str(REPO / "scripts"))
from installer_recovery_composition import recover_failed_installer_upgrade  # noqa: E402


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    database_path = tmp_path / "phase29-recovery.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    command.upgrade(config, "head")
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "lifecycle.recovery.recovery_supervisor")


@pytest.fixture()
def blobs(
    tmp_path: pathlib.Path, pdp: PolicyDecisionPoint
) -> ArtifactBlobStore:
    blob_pep = PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")
    return ArtifactBlobStore(tmp_path / "blobs", blob_pep)


def _receipt(path: StableCandidatePath, candidate_id: str):
    receipt = path.begin_candidate(candidate_id=candidate_id)
    for stage in path.stages()[2:-1]:
        receipt = path.advance(receipt, to_stage=stage)
    return path.promotion_receipt(receipt)


def test_failed_upgrade_uses_real_supervisor_and_real_evidence(
    tmp_path: pathlib.Path,
    engine: Engine,
    pep: PolicyEnforcementPoint,
    blobs: ArtifactBlobStore,
) -> None:
    path = StableCandidatePath.load(REPO)
    pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
    good = address_of(b"ARKALI_Setup.exe:0.1.0")
    bad = address_of(b"ARKALI_Setup.exe:0.1.1-bad")
    pointer.promote(_receipt(path, "good"), revision_id=good, candidate_id="good")
    pointer.promote(_receipt(path, "bad"), revision_id=bad, candidate_id="bad")

    with unit_of_work(create_session_factory(engine)) as session:
        record = recover_failed_installer_upgrade(
            session=session,
            pep=pep,
            pointer=pointer,
            blobs=blobs,
            candidate_id="bad",
            target_revision_id=good,
            failure_detail="installed candidate backend health check failed",
        )

    assert record.from_revision_id == bad
    assert record.to_revision_id == good
    assert pointer.current().revision_id == good  # type: ignore[union-attr]
    assert len(record.evidence_record_hashes) == 3
    with unit_of_work(create_session_factory(engine)) as session:
        chain = AuditChain(session, pep, REPO)
        assert chain.verify().verified
        assert {item.requirement_id for item in chain.records()} == {
            "ARK-REQ-0160",
            "ARK-REQ-0338",
            "ARK-REQ-0339",
        }


def test_installer_composition_has_no_second_rollback_or_file_restore() -> None:
    source_path = REPO / "scripts/installer_recovery_composition.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert ".rollback_to(" not in source
    assert source.count("RecoverySupervisor(") == 1
    assert source.count("supervisor.rollback(") == 1
    for forbidden in ("shutil", "os.replace", "subprocess", "openai", "ollama"):
        assert forbidden not in source
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"rollback", "restore", "promote"}
        for node in ast.walk(tree)
    )
