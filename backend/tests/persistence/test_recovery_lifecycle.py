"""ARK-REQ-0153 / ARK-REQ-0335 backup lifecycle evidence (T11 + T5).

The canonical proof: A -> backup -> mutate to B -> restore -> verify A.
A file copy alone is FAIL, and a backup is not verified until an actual restore
proves it. Every test uses real SQLite files, a real PDP loaded from the
authority map, and the real BackupRestore state machine.

These controls establish the package-level result. They do NOT discharge the
requirements: discharge belongs to the Phase 5 traceability record, phase report
and gate run, none of which exists yet.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from arkali.control.policy.operation_class import Decision
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.kernel.contracts.state_machine_errors import (
    ForbiddenTransition,
    GuardRejected,
    IllegalTransition,
    TerminalStateEscape,
)
from arkali.kernel.persistence.backup import SQLITE_MAGIC
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import applied_revision, head_revision
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.recovery.backup_restore_state_machine import DEFINITION, build
from arkali.lifecycle.recovery.backup_service import (
    ACTOR,
    BackupVerificationFailed,
    RecoveryService,
)
from arkali.lifecycle.recovery.manifest import (
    ManifestError,
    manifest_path,
    read_manifest,
    write_manifest,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
SERVICE_SOURCE = BACKEND / "arkali/lifecycle/recovery/backup_service.py"


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "lifecycle.recovery.backup")


@pytest.fixture()
def service(pep: PolicyEnforcementPoint) -> RecoveryService:
    return RecoveryService(pep)


@pytest.fixture()
def live_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "live.db"


def alembic_config(database_path: pathlib.Path) -> Config:
    """The real migration chain, so the database carries a real revision."""
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


@pytest.fixture()
def engine(live_path: pathlib.Path) -> Iterator[Engine]:
    command.upgrade(alembic_config(live_path), "head")
    built = create_persistence_engine(sqlite_url(live_path))
    with unit_of_work(create_session_factory(built)) as session:
        registry = ProjectRegistry(session)
        registry.create_project("prj-a", "State A")
        registry.create_revision("prj-a", "rev-a")
    yield built
    built.dispose()


def mutate_to_b(engine: Engine) -> None:
    with unit_of_work(create_session_factory(engine)) as session:
        registry = ProjectRegistry(session)
        registry.transition("prj-a", "SPECIFIED")
        registry.create_project("prj-b", "Added After Backup")


def holds_state_a(engine: Engine) -> bool:
    """A real verifier: state A present, state B absent."""
    with unit_of_work(create_session_factory(engine)) as session:
        registry = ProjectRegistry(session)
        project = registry.get("prj-a")
        return (
            project is not None
            and project.lifecycle_state == "DRAFT"
            and registry.revision("rev-a") is not None
            and registry.get("prj-b") is None
        )


def backup_of(service: RecoveryService, engine: Engine, tmp_path: pathlib.Path,
              backup_id: str = "bk-1") -> object:
    return service.create_backup(engine, tmp_path / "backups", backup_id)


class TestManifest:
    def test_manifest_records_what_a_restore_decision_needs(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        backup = backup_of(service, engine, tmp_path)
        manifest = backup.manifest
        assert manifest.backup_id == "bk-1"
        assert manifest.source_database == "live.db"
        assert manifest.size_bytes == backup.image.stat().st_size
        assert len(manifest.digest) == 64
        assert manifest_path(backup.image).is_file()

    def test_manifest_carries_no_host_path_and_no_secret(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 15: no raw secret, and no operator filesystem layout."""
        backup = backup_of(service, engine, tmp_path)
        body = manifest_path(backup.image).read_text(encoding="utf-8")
        for term in ("secret", "password", "token", "api_key", "credential"):
            assert term not in body.lower()
        assert str(tmp_path) not in body
        assert "/" not in backup.manifest.source_database

    def test_an_unreadable_manifest_is_refused(self, tmp_path: pathlib.Path) -> None:
        image = tmp_path / "x.db"
        image.write_bytes(SQLITE_MAGIC)
        manifest_path(image).write_text("{not json", encoding="utf-8")
        with pytest.raises(ManifestError, match="readable JSON"):
            read_manifest(image)

    def test_a_future_major_manifest_version_is_refused(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        backup = backup_of(service, engine, tmp_path)
        future = backup.manifest.model_copy(update={"manifest_version": "2.0.0"})
        write_manifest(backup.image, future)
        with pytest.raises(ManifestError, match="major version"):
            read_manifest(backup.image)


class TestCanonicalProof:
    def test_a_backup_b_restore_verify_a(
        self, service: RecoveryService, engine: Engine, live_path: pathlib.Path,
        tmp_path: pathlib.Path
    ) -> None:
        """ARK-REQ-0335: A -> backup -> B -> restore -> verify A."""
        backup = backup_of(service, engine, tmp_path)
        assert backup.state == "BACKUP_RUNNING"

        mutate_to_b(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            assert ProjectRegistry(session).get("prj-b") is not None
        engine.dispose()

        service.prove_by_restore(backup, tmp_path / "scratch.db", holds_state_a)
        assert backup.state == "BACKUP_VERIFIED"

        service.restore(backup, live_path, holds_state_a)
        assert backup.state == "RESTORE_VERIFIED"

        reopened = create_persistence_engine(sqlite_url(live_path))
        try:
            assert holds_state_a(reopened)
            assert applied_revision(reopened) == backup.manifest.schema_revision
        finally:
            reopened.dispose()

    def test_b_cannot_survive_a_successful_verification(
        self, service: RecoveryService, engine: Engine, live_path: pathlib.Path,
        tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 18: verification must not pass while B is present."""
        backup = backup_of(service, engine, tmp_path)
        mutate_to_b(engine)
        engine.dispose()
        service.prove_by_restore(backup, tmp_path / "scratch.db", holds_state_a)
        service.restore(backup, live_path, holds_state_a)
        reopened = create_persistence_engine(sqlite_url(live_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                assert ProjectRegistry(session).get("prj-b") is None
        finally:
            reopened.dispose()


class TestFileCopyAloneIsNotVerification:
    def test_a_fresh_backup_is_not_verified(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 1 and 2: bytes exist != backup verified."""
        backup = backup_of(service, engine, tmp_path)
        assert backup.image.is_file() and backup.image.stat().st_size > 0
        assert manifest_path(backup.image).is_file()
        assert backup.state != "BACKUP_VERIFIED"
        assert backup.state == "BACKUP_RUNNING"

    def test_the_guard_refuses_promotion_without_a_restore_proof(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """The exact reason: `restore_proof_guard` rejects, not something else."""
        backup = backup_of(service, engine, tmp_path)
        with pytest.raises(GuardRejected):
            backup.machine.apply("BACKUP_VERIFIED")
        with pytest.raises(GuardRejected):
            backup.machine.apply("BACKUP_VERIFIED", {"restore_proven": False})
        assert backup.state == "BACKUP_RUNNING"

    def test_a_hand_copied_image_still_cannot_be_promoted(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """A plain filesystem copy produces bytes and no verified lifecycle."""
        import shutil

        backup = backup_of(service, engine, tmp_path)
        copied = tmp_path / "hand-copy.db"
        shutil.copy2(backup.image, copied)
        assert copied.stat().st_size == backup.image.stat().st_size
        assert build().start("PLANNED").state == "PLANNED"
        with pytest.raises(GuardRejected):
            backup.machine.apply("BACKUP_VERIFIED", {})


class TestIntegrityAndCompatibilityGates:
    def test_corrupt_image_bytes_are_rejected(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 3."""
        backup = backup_of(service, engine, tmp_path)
        raw = bytearray(backup.image.read_bytes())
        raw[len(SQLITE_MAGIC) : len(SQLITE_MAGIC) + 256] = b"\x00" * 256
        backup.image.write_bytes(bytes(raw))
        with pytest.raises(ManifestError, match="integrity mismatch"):
            service.prove_by_restore(backup, tmp_path / "s.db", holds_state_a)
        assert backup.state == "FAILED"

    def test_a_tampered_digest_is_rejected(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 4: rewriting the manifest cannot bless the image."""
        backup = backup_of(service, engine, tmp_path)
        tampered = backup.manifest.model_copy(update={"digest": "0" * 64})
        write_manifest(backup.image, tampered)
        with pytest.raises(ManifestError, match="differs from"):
            service.prove_by_restore(backup, tmp_path / "s.db", holds_state_a)
        assert backup.state == "FAILED"

    def test_a_truncated_image_is_rejected_on_size(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        backup = backup_of(service, engine, tmp_path)
        backup.image.write_bytes(backup.image.read_bytes()[:2048])
        with pytest.raises(ManifestError, match="size mismatch"):
            service.prove_by_restore(backup, tmp_path / "s.db", holds_state_a)

    def test_a_missing_manifest_component_is_rejected(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 5."""
        backup = backup_of(service, engine, tmp_path)
        manifest_path(backup.image).unlink()
        with pytest.raises(ManifestError, match="component missing"):
            service.prove_by_restore(backup, tmp_path / "s.db", holds_state_a)

    def test_a_missing_image_component_is_rejected(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        backup = backup_of(service, engine, tmp_path)
        backup.image.unlink()
        with pytest.raises(ManifestError, match="component missing"):
            service.prove_by_restore(backup, tmp_path / "s.db", holds_state_a)

    def test_an_incompatible_schema_revision_is_rejected(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 6 and 7: manifest/database revision mismatch."""
        backup = backup_of(service, engine, tmp_path)
        # F-0032: the chain head is derived, never transcribed. A literal here
        # pinned the head that was current when the test was written and
        # expired the moment a legitimate migration was added.
        assert backup.manifest.schema_revision == head_revision(BACKEND)
        wrong = backup.manifest.model_copy(
            update={"schema_revision": "9999_not_a_real_revision"}
        )
        write_manifest(backup.image, wrong)
        declared = type(backup)(backup.image, wrong, backup.machine)
        with pytest.raises(ManifestError, match="revision mismatch"):
            service.prove_by_restore(declared, tmp_path / "s2.db", holds_state_a)
        assert declared.state == "FAILED"

    def test_a_manifest_without_a_revision_is_incompatible(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        backup = backup_of(service, engine, tmp_path)
        assert not backup.manifest.model_copy(
            update={"schema_revision": None}
        ).compatible_with(None)


class TestVerificationFailure:
    def test_a_verifier_that_says_no_prevents_promotion(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 8 and 9: verification mismatch cannot be verified."""
        backup = backup_of(service, engine, tmp_path)
        with pytest.raises(BackupVerificationFailed):
            service.prove_by_restore(backup, tmp_path / "s.db", lambda _e: False)
        assert backup.state == "FAILED"

    def test_a_failed_proof_leaves_the_source_usable(
        self, service: RecoveryService, engine: Engine, live_path: pathlib.Path,
        tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 17."""
        backup = backup_of(service, engine, tmp_path)
        with pytest.raises(BackupVerificationFailed):
            service.prove_by_restore(backup, tmp_path / "s.db", lambda _e: False)
        with unit_of_work(create_session_factory(engine)) as session:
            assert ProjectRegistry(session).get("prj-a") is not None


class TestStateMachineIntegration:
    def test_the_service_drives_the_canonical_machine(self) -> None:
        assert DEFINITION.machine == "BackupRestore"
        assert DEFINITION.authority == "lifecycle.recovery"

    def test_illegal_transition_is_rejected(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 10."""
        backup = backup_of(service, engine, tmp_path)
        with pytest.raises(IllegalTransition):
            backup.machine.apply("RESTORE_RUNNING")

    def test_terminal_escape_is_rejected(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 11."""
        backup = backup_of(service, engine, tmp_path)
        backup.machine.apply("FAILED")
        for target in ("BACKUP_RUNNING", "BACKUP_VERIFIED", "RESTORE_RUNNING"):
            with pytest.raises(TerminalStateEscape):
                backup.machine.apply(target)

    def test_restore_before_proof_is_refused_by_the_machine(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """No public service method can reach a restore without the proof."""
        backup = backup_of(service, engine, tmp_path)
        with pytest.raises((IllegalTransition, ForbiddenTransition)):
            service.restore(backup, tmp_path / "target.db", holds_state_a)

    def test_recovery_declares_no_shadow_transition_authority(self) -> None:
        """NEGATIVE CONTROL 16: no second relation, no copied state constants."""
        tree = ast.parse(SERVICE_SOURCE.read_text(encoding="utf-8"))
        literals = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert literals & set(DEFINITION.states) == set()
        constructed = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "StateMachineDefinition" not in constructed


class TestPolicyEnforcement:
    def test_every_decision_is_audited_through_the_phase_4_surface(
        self, service: RecoveryService, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        backup = backup_of(service, engine, tmp_path)
        service.prove_by_restore(backup, tmp_path / "s.db", holds_state_a)
        trail = service.audit_trail
        assert trail
        assert all(r.actor == ACTOR for r in trail)
        assert {r.operation_class for r in trail} == {
            "READ_FILE", "WRITE_WORKSPACE_FILE"
        }
        assert all(r.decision is Decision.AUTO for r in trail)

    def test_write_stable_file_remains_denied_to_this_actor(
        self, pep: PolicyEnforcementPoint
    ) -> None:
        """NEGATIVE CONTROL 13."""
        with pytest.raises(PolicyDenied):
            pep.enforce(
                PolicyRequest(
                    operation_class="WRITE_STABLE_FILE", trust_tier="TRUST-0",
                    actor=ACTOR,
                )
            )

    def test_rollback_stable_remains_denied_to_this_actor(
        self, pep: PolicyEnforcementPoint
    ) -> None:
        """NEGATIVE CONTROL 14: this package is not Stable rollback."""
        with pytest.raises(PolicyDenied):
            pep.enforce(
                PolicyRequest(
                    operation_class="ROLLBACK_STABLE", trust_tier="TRUST-0",
                    actor=ACTOR,
                )
            )

    def test_the_service_never_requests_a_stable_operation(self) -> None:
        """NEGATIVE CONTROL 12: policy cannot be bypassed by asking for less."""
        body = SERVICE_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(body)
        requested = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert "WRITE_STABLE_FILE" not in requested
        assert "ROLLBACK_STABLE" not in requested

    def test_a_denied_policy_stops_the_backup(
        self, pdp: PolicyDecisionPoint, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL 12: enforcement is real, not decorative.

        A PEP whose PDP denies the write must stop the flow. The refusal comes
        from the policy layer, not from a check inside the recovery service.
        """
        class DenyingPoint(PolicyEnforcementPoint):
            def require_auto(self, request: PolicyRequest) -> object:
                raise PolicyDenied(f"denied for control: {request.operation_class}")

        denying = RecoveryService(DenyingPoint(pdp, "denying-surface"))
        with pytest.raises(PolicyDenied):
            denying.create_backup(engine, tmp_path / "b", "bk-denied")
