#!/usr/bin/env python3
"""CLI entrypoint for `engineering.factory.product_registration.
register_accepted_candidate_as_managed_product` — the composition D-027
assigns to `engineering.factory` (`docs/build/OPEN_BLOCKERS.md` DEF-009 /
D-027, closed by a later human governance ruling authorizing exactly this
behaviour).

`run_golden_acceptance.py` already calls this same composition function
automatically, in-process, immediately after it records a real `ACCEPTED`
ledger entry — a normal operator never needs to run this script. It exists
for the one real recovery case failure atomicity requires: if that
automatic call could not complete (e.g. the Command Center database was
briefly unavailable), the ACCEPTED ledger entry itself is already durably
recorded and terminal, so re-running acceptance is not possible; this
script re-invokes registration alone. `register_accepted_candidate_as_
managed_product` is idempotent (`product_registration.py`'s own module
docstring), so running this against an already-registered candidate is a
safe no-op, not a duplicate.

The two persistence stores this touches are the same, real, already-
production stores `surfaces.command`'s own app and `run_factory_worker.py`
already use unchanged — `var/command_center.db` (`ProjectRegistry`) and
`var/factory/evidence/repair-evidence.db` (`ArtifactStore`) — never a new
database.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.control.registry.project.registry import ProjectRegistry  # noqa: E402
from arkali.engineering.candidate.ledger import CandidateLedger  # noqa: E402
from arkali.engineering.factory.errors import CandidateNotAcceptedError  # noqa: E402
from arkali.engineering.factory.product_registration import (  # noqa: E402
    register_accepted_candidate_as_managed_product,
)
from arkali.evidence.artifact.blob_store import ArtifactBlobStore  # noqa: E402
from arkali.evidence.artifact.store import ArtifactStore  # noqa: E402
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
    sqlite_url,
)
from arkali.kernel.persistence.migrations import ALEMBIC_INI  # noqa: E402
from arkali.kernel.persistence.session import (  # noqa: E402
    create_session_factory,
    unit_of_work,
)


def _upgraded_engine(db_path: pathlib.Path):  # noqa: ANN202
    db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(ROOT / "backend" / ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sqlite_url(db_path))
    command.upgrade(cfg, "head")
    return create_persistence_engine(sqlite_url(db_path))


def register(candidate_id: str) -> dict[str, object]:
    """Real DB/session wiring around the pure composition call — the same
    shape `run_golden_acceptance.py`'s own automatic call uses, duplicated
    here rather than shared, matching this repository's existing precedent
    of each script owning its own small persistence bootstrap
    (`run_factory_worker.py`'s own `_freeze`)."""
    ledger = CandidateLedger(ROOT / "var" / "factory" / "candidates" / "_ledger")
    pdp = PolicyDecisionPoint.load(ROOT)

    command_center_engine = _upgraded_engine(ROOT / "var" / "command_center.db")
    evidence_engine = _upgraded_engine(ROOT / "var" / "factory" / "evidence" / "repair-evidence.db")
    blobs = ArtifactBlobStore(
        ROOT / "var" / "factory" / "evidence" / "blobs",
        PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"),
    )
    try:
        with unit_of_work(create_session_factory(command_center_engine)) as project_session, \
             unit_of_work(create_session_factory(evidence_engine)) as evidence_session:
            registry = ProjectRegistry(project_session)
            artifacts = ArtifactStore(evidence_session, blobs)
            outcome = register_accepted_candidate_as_managed_product(
                candidate_id, ledger=ledger, registry=registry, artifacts=artifacts,
            )
            return {
                "outcome": "REGISTERED",
                "candidate_id": candidate_id,
                "project_id": outcome.project.project_id,
                "revision_id": outcome.revision.revision_id,
                "provenance_ref": outcome.provenance_ref,
                "created": outcome.created,
            }
    finally:
        command_center_engine.dispose()
        evidence_engine.dispose()


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    args = parser.parse_args(argv[1:])

    try:
        result = register(args.candidate_id)
    except CandidateNotAcceptedError as error:
        print(json.dumps({"outcome": "CANDIDATE_NOT_ACCEPTED", "error": str(error)}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
