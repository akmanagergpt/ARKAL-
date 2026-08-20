#!/usr/bin/env python3
"""Real failed-installer refusal followed by the existing C-32 rollback.

The candidate and install locations are deliberately fixed beneath this
repository's ignored ``artifacts`` directory.  This is an acceptance runner,
not a frontend/native command surface.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

from alembic import command
from alembic.config import Config
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.release.stable_path import StableCandidatePath
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
GOOD_INSTALLER = (
    ROOT
    / "src-tauri"
    / "target"
    / "release"
    / "bundle"
    / "nsis"
    / "ARKALI_0.1.1_x64-setup.exe"
)
INSTALL_DIR = ROOT / "artifacts" / "phase29-real-install"
STATE_DIR = ROOT / "artifacts" / "phase29-recovery"
FAILED_INSTALLER = STATE_DIR / "ARKALI_0.1.2_corrupt_Setup.exe"

sys.path.insert(0, str(ROOT / "scripts"))
from installer_recovery_composition import (
    recover_failed_installer_upgrade,
)


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _receipt(path: StableCandidatePath, candidate_id: str):
    receipt = path.begin_candidate(candidate_id=candidate_id)
    for stage in path.stages()[2:-1]:
        receipt = path.advance(receipt, to_stage=stage)
    return path.promotion_receipt(receipt)


def _migration_config(database: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database))
    return config


def main() -> int:
    if not GOOD_INSTALLER.is_file() or not INSTALL_DIR.is_dir():
        raise FileNotFoundError("real candidate installer or isolated install is absent")
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # A truncated NSIS candidate is a real non-executable failed upgrade input.
    # The known-good installer and installed data are never modified here.
    with GOOD_INSTALLER.open("rb") as source, FAILED_INSTALLER.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
        target.truncate(4096)
    good_revision = _sha256(GOOD_INSTALLER)
    failed_revision = _sha256(FAILED_INSTALLER)

    failed_exit: int | None = None
    failed_error: str | None = None
    try:
        attempt = subprocess.run(
            [str(FAILED_INSTALLER), "/S", f"/D={INSTALL_DIR}"],
            check=False,
            timeout=30,
        )
        failed_exit = attempt.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        failed_error = f"{type(exc).__name__}: {exc}"
    if failed_exit == 0:
        raise RuntimeError("corrupt installer unexpectedly reported success")

    database = STATE_DIR / "recovery-evidence.db"
    if database.exists():
        database.unlink()
    command.upgrade(_migration_config(database), "head")
    engine = create_persistence_engine(sqlite_url(database))
    pdp = PolicyDecisionPoint.load(ROOT)
    recovery_pep = PolicyEnforcementPoint(
        pdp, "lifecycle.recovery.recovery_supervisor"
    )
    blob_pep = PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")
    blobs = ArtifactBlobStore(STATE_DIR / "blobs", blob_pep)
    path = StableCandidatePath.load(ROOT)
    pointer = StableRevisionPointer(path, STATE_DIR / "stable_pointer.json")
    pointer.promote(
        _receipt(path, "installer-0.1.1"),
        revision_id=good_revision,
        candidate_id="installer-0.1.1",
    )
    pointer.promote(
        _receipt(path, "installer-0.1.2-corrupt"),
        revision_id=failed_revision,
        candidate_id="installer-0.1.2-corrupt",
    )
    try:
        with unit_of_work(create_session_factory(engine)) as session:
            record = recover_failed_installer_upgrade(
                session=session,
                pep=recovery_pep,
                pointer=pointer,
                blobs=blobs,
                candidate_id="installer-0.1.2-corrupt",
                target_revision_id=good_revision,
                failure_detail=failed_error or f"installer exited {failed_exit}",
            )
    finally:
        engine.dispose()

    # The C-32 decision selects the already-verified identity. Reinstalling
    # that exact mapped artifact restores files without touching app-data.
    installers = {good_revision: GOOD_INSTALLER}
    selected = installers[record.to_revision_id]
    recovery_install = subprocess.run(
        [str(selected), "/S", f"/D={INSTALL_DIR}"], check=False, timeout=60
    )
    if recovery_install.returncode != 0:
        raise RuntimeError(f"known-good recovery installer exited {recovery_install.returncode}")

    result = {
        "result": "PASS",
        "failed_installer": FAILED_INSTALLER.name,
        "failed_revision": failed_revision,
        "failed_exit": failed_exit,
        "failed_error": failed_error,
        "recovery_contract": "C-32",
        "from_revision": record.from_revision_id,
        "to_revision": record.to_revision_id,
        "pointer_current": pointer.current().revision_id,
        "known_good_reinstall_exit": recovery_install.returncode,
        "evidence_records": len(record.evidence_record_hashes),
    }
    (STATE_DIR / "journey.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
