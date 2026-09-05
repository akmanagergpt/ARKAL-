"""Real, over-real-persistence tests for `engineering.product_change.
restore` (Managed Product Revision History + Restore-as-New Convergence).

Every test drives real owners over real, isolated persistence — the
identical fixture shape `test_product_change.py` already established
(a real `ProjectRegistry`, a real `ArtifactStore`+`ArtifactBlobStore`, a
real `WorkspaceAuthority`, all isolated per test via `tmp_path`). A
`_PoisonModel` test double proves — mechanically, not by inspection —
that a pure restore never invokes a model.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.product_change.errors import UnknownSourceBasisRevisionError
from arkali.engineering.product_change.modification import ModificationWiring
from arkali.engineering.product_change.promotion import promote_modification
from arkali.engineering.product_change.restore import prepare_restore
from arkali.engineering.product_change.revision_resolution import (
    _MANAGED_PRODUCT_PROVENANCE_SPEC,
)
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.session import (
    create_base_schema,
    create_session_factory,
    unit_of_work,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


class _PoisonModel:
    """Raises unconditionally — proves a pure restore never calls
    `ModificationWiring.model.infer`, mechanically, not by omission."""

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0):  # noqa: ANN001, ANN201
        raise AssertionError("prepare_restore must never invoke a model")


class _StubCandidateSource:
    def __init__(self, directories: dict[str, pathlib.Path]) -> None:
        self._directories = directories

    def source_dir(self, candidate_id: str) -> pathlib.Path:
        return self._directories[candidate_id]


class _AlwaysGrant:
    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str, revision_identity: str,
    ) -> bool:
        return gate_id == "HUMAN_GATE_3" and operation_class == "MANAGED_PRODUCT_REVISION_PROMOTION"


@pytest.fixture()
def registry_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(tmp_path / "command_center.db"))
    create_base_schema(built)
    yield built
    built.dispose()


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def artifact_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    from alembic import command
    from alembic.config import Config
    from arkali.kernel.persistence.migrations import ALEMBIC_INI

    db_path = tmp_path / "evidence.db"
    config = Config(str(REPO / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(db_path))
    command.upgrade(config, "head")
    built = create_persistence_engine(sqlite_url(db_path))
    yield built
    built.dispose()


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, pdp: PolicyDecisionPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(
        tmp_path / "blobs", PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"),
    )


def _register_candidate_revision(
    project_id: str, candidate_id: str, registry_engine: Engine, artifact_engine: Engine,
    blobs: ArtifactBlobStore,
) -> str:
    """A real, minimal Factory-origin revision, appended to whatever the
    project already has (never assuming this is the first)."""
    with unit_of_work(create_session_factory(artifact_engine)) as evidence_session:
        artifacts = ArtifactStore(evidence_session, blobs)
        payload = json.dumps({"candidate_id": candidate_id}).encode("utf-8")
        provenance_ref = artifacts.register(
            payload,
            ProvenanceInput(
                producer_agent="engineering.factory", provider_model="local",
                task_id=candidate_id, specification_version=_MANAGED_PRODUCT_PROVENANCE_SPEC,
                context_hash=candidate_id,
            ),
        )
    with unit_of_work(create_session_factory(registry_engine)) as session:
        registry = ProjectRegistry(session)
        if registry.get(project_id) is None:
            registry.create_project(project_id, f"Test Product {project_id}")
        next_seq = registry.next_sequence(project_id)
        revision_id = f"{project_id}-r{next_seq}"
        registry.create_revision(project_id, revision_id, provenance_ref=provenance_ref)
    return revision_id


class TestPrepareRestore:
    def test_unknown_source_basis_revision_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_dir = tmp_path / "candidate-r1"
        candidate_dir.mkdir()
        (candidate_dir / "app.py").write_text("print('r1')\n", encoding="utf-8")
        _register_candidate_revision("p1", "candidate-r1", registry_engine, artifact_engine, blobs)

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource({"candidate-r1": candidate_dir}),
                workspace_allocator=WorkspaceAuthority(tmp_path / "restore-ws"),
                model=_PoisonModel(), model_id="unused",
            )
            with pytest.raises(UnknownSourceBasisRevisionError):
                prepare_restore(
                    "p1", "p1-r999", registry=ProjectRegistry(session), wiring=wiring,
                )

    def test_a_revision_of_a_different_project_is_refused_as_source_basis(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_a = tmp_path / "candidate-a"
        candidate_a.mkdir()
        (candidate_a / "app.py").write_text("print('a')\n", encoding="utf-8")
        _register_candidate_revision("p1", "candidate-a", registry_engine, artifact_engine, blobs)

        candidate_b = tmp_path / "candidate-b"
        candidate_b.mkdir()
        (candidate_b / "app.py").write_text("print('b')\n", encoding="utf-8")
        other_revision = _register_candidate_revision(
            "p2", "candidate-b", registry_engine, artifact_engine, blobs,
        )

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource(
                    {"candidate-a": candidate_a, "candidate-b": candidate_b},
                ),
                workspace_allocator=WorkspaceAuthority(tmp_path / "restore-ws"),
                model=_PoisonModel(), model_id="unused",
            )
            with pytest.raises(UnknownSourceBasisRevisionError):
                prepare_restore(
                    "p1", other_revision, registry=ProjectRegistry(session), wiring=wiring,
                )

    def test_restoring_an_older_revision_computes_a_real_diff_and_invokes_no_model(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_r1 = tmp_path / "candidate-r1"
        candidate_r1.mkdir()
        (candidate_r1 / "app.py").write_text("print('original')\n", encoding="utf-8")
        (candidate_r1 / "shared.py").write_text("VALUE = 1\n", encoding="utf-8")
        r1 = _register_candidate_revision("p1", "candidate-r1", registry_engine, artifact_engine, blobs)

        candidate_r2 = tmp_path / "candidate-r2"
        candidate_r2.mkdir()
        (candidate_r2 / "app.py").write_text("print('edited')\n", encoding="utf-8")
        (candidate_r2 / "shared.py").write_text("VALUE = 1\n", encoding="utf-8")
        (candidate_r2 / "new_file.py").write_text("NEW = True\n", encoding="utf-8")
        r2 = _register_candidate_revision("p1", "candidate-r2", registry_engine, artifact_engine, blobs)

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource(
                    {"candidate-r1": candidate_r1, "candidate-r2": candidate_r2},
                ),
                workspace_allocator=WorkspaceAuthority(tmp_path / "restore-ws"),
                model=_PoisonModel(), model_id="unused",  # never invoked -- see class docstring
            )
            phases: list[str] = []
            prepared = prepare_restore(
                "p1", r1, registry=ProjectRegistry(session), wiring=wiring,
                on_phase=lambda phase, detail: phases.append(phase),
            )

        assert prepared.base_revision_id == r2  # base = current, r2
        # The restored tree matches r1 exactly: app.py reverted, new_file.py removed.
        assert (prepared.product_root / "app.py").read_text(encoding="utf-8") == "print('original')\n"
        assert not (prepared.product_root / "new_file.py").exists()
        assert (prepared.product_root / "shared.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        assert prepared.verification.passed is True
        assert r1 in prepared.plan.request_text
        assert "base_revision_resolved" in phases
        assert "source_basis_resolved" in phases

    def test_a_real_non_utf8_build_artifact_is_excluded_rather_than_crashing(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        """Real, reproduced regression: `golden-work-129`'s own real
        candidate directory carries `tests/__pycache__/test_app.
        cpython-313-pytest-9.1.1.pyc`, a real, honest side effect of a
        real prior `pytest` run -- not valid UTF-8. A restore must
        exclude it (never authored product source) rather than crash."""
        candidate_r1 = tmp_path / "candidate-r1"
        (candidate_r1 / "tests" / "__pycache__").mkdir(parents=True)
        (candidate_r1 / "app.py").write_text("print('original')\n", encoding="utf-8")
        (candidate_r1 / "tests" / "__pycache__" / "test_app.cpython-313.pyc").write_bytes(
            b"\xf3\x0d\x0d\x0a\x00\x00\x00\x00binary bytecode, not utf-8",
        )
        r1 = _register_candidate_revision("p1", "candidate-r1", registry_engine, artifact_engine, blobs)

        candidate_r2 = tmp_path / "candidate-r2"
        candidate_r2.mkdir()
        (candidate_r2 / "app.py").write_text("print('edited')\n", encoding="utf-8")
        _register_candidate_revision("p1", "candidate-r2", registry_engine, artifact_engine, blobs)

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource(
                    {"candidate-r1": candidate_r1, "candidate-r2": candidate_r2},
                ),
                workspace_allocator=WorkspaceAuthority(tmp_path / "restore-ws"),
                model=_PoisonModel(), model_id="unused",
            )
            prepared = prepare_restore("p1", r1, registry=ProjectRegistry(session), wiring=wiring)

        assert (prepared.product_root / "app.py").read_text(encoding="utf-8") == "print('original')\n"
        assert prepared.verification.passed is True
        assert not any(op.path.endswith(".pyc") for op in prepared.plan.operations)

    def test_a_real_crash_after_workspace_allocation_leaves_no_orphan_directory(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Real, reproduced regression: the first live restore attempt
        against `golden-work-129` crashed inside `_diff_operations` (a
        real non-UTF8 `.pyc` build artifact, fixed separately) and left a
        real `var/factory/changes/restore-*` directory behind forever --
        `prepare_restore` did not clean up on its own internal failure,
        unlike `prepare_modification`'s own provider-response failures.
        Proven fixed here with an independent, unrelated forced failure
        (never re-relying on the original `.pyc` trigger, which its own
        sibling test already covers as a functional exclusion, not a
        crash)."""
        import arkali.engineering.product_change.restore as restore_module

        candidate_dir = tmp_path / "candidate-r1"
        candidate_dir.mkdir()
        (candidate_dir / "app.py").write_text("print('original')\n", encoding="utf-8")
        r1 = _register_candidate_revision("p1", "candidate-r1", registry_engine, artifact_engine, blobs)

        def _boom(*args: object, **kwargs: object):  # noqa: ANN202
            raise RuntimeError("simulated post-allocation crash")

        monkeypatch.setattr(restore_module, "verify_changeset", _boom)

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource({"candidate-r1": candidate_dir}),
                workspace_allocator=WorkspaceAuthority(tmp_path / "restore-ws"),
                model=_PoisonModel(), model_id="unused",
            )
            with pytest.raises(RuntimeError, match="simulated post-allocation crash"):
                prepare_restore("p1", r1, registry=ProjectRegistry(session), wiring=wiring)

        remaining = list((tmp_path / "restore-ws").glob("restore-*"))
        assert remaining == [], f"orphaned restore workspace(s) left behind: {remaining}"

    def test_restoring_the_current_revision_to_itself_is_a_real_but_harmless_no_op(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_dir = tmp_path / "candidate-r1"
        candidate_dir.mkdir()
        (candidate_dir / "app.py").write_text("print('same')\n", encoding="utf-8")
        r1 = _register_candidate_revision("p1", "candidate-r1", registry_engine, artifact_engine, blobs)

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            wiring = ModificationWiring(
                artifacts=ArtifactStore(art_session, blobs),
                candidate_source_resolver=_StubCandidateSource({"candidate-r1": candidate_dir}),
                workspace_allocator=WorkspaceAuthority(tmp_path / "restore-ws"),
                model=_PoisonModel(), model_id="unused",
            )
            prepared = prepare_restore(
                "p1", r1, registry=ProjectRegistry(session), wiring=wiring,
            )
        # ChangePlan.operations requires at least one entry even when the
        # two trees are byte-identical -- proven real, not merely accepted.
        assert len(prepared.plan.operations) >= 1
        assert prepared.verification.passed is True
        assert (prepared.product_root / "app.py").read_text(encoding="utf-8") == "print('same')\n"


class TestRestorePromotion:
    def test_a_promoted_restore_appends_exactly_one_new_revision_and_becomes_current(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
        tmp_path: pathlib.Path,
    ) -> None:
        candidate_r1 = tmp_path / "candidate-r1"
        candidate_r1.mkdir()
        (candidate_r1 / "app.py").write_text("print('original')\n", encoding="utf-8")
        r1 = _register_candidate_revision("p1", "candidate-r1", registry_engine, artifact_engine, blobs)

        candidate_r2 = tmp_path / "candidate-r2"
        candidate_r2.mkdir()
        (candidate_r2 / "app.py").write_text("print('edited')\n", encoding="utf-8")
        r2 = _register_candidate_revision("p1", "candidate-r2", registry_engine, artifact_engine, blobs)

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as art_session:
            artifacts = ArtifactStore(art_session, blobs)
            wiring = ModificationWiring(
                artifacts=artifacts,
                candidate_source_resolver=_StubCandidateSource(
                    {"candidate-r1": candidate_r1, "candidate-r2": candidate_r2},
                ),
                workspace_allocator=WorkspaceAuthority(tmp_path / "restore-ws"),
                model=_PoisonModel(), model_id="unused",
            )
            prepared = prepare_restore("p1", r1, registry=ProjectRegistry(session), wiring=wiring)
            registry = ProjectRegistry(session)
            revision = promote_modification(
                "p1", prepared, registry=registry, artifacts=artifacts,
                human_gates=_AlwaysGrant(), issuer_identity="test",
            )

            assert revision.sequence == 3
            assert revision.revision_id not in (r1, r2)
            all_revisions = registry.revisions_of("p1")
            assert {r.revision_id for r in all_revisions} == {r1, r2, revision.revision_id}
            current = max(all_revisions, key=lambda r: r.sequence)
            assert current.revision_id == revision.revision_id

            # Double-promote is idempotent: the SAME prepared proposal
            # promoted twice returns the identical revision, never a
            # second one (content-addressed archive re-registration).
            revision_again = promote_modification(
                "p1", prepared, registry=registry, artifacts=artifacts,
                human_gates=_AlwaysGrant(), issuer_identity="test",
            )
            assert revision_again.revision_id == revision.revision_id
            assert len(registry.revisions_of("p1")) == 3

            # Historical revisions are byte-unchanged: r1's own real
            # candidate source was never touched by this whole cycle.
            assert (candidate_r1 / "app.py").read_text(encoding="utf-8") == "print('original')\n"
            assert (candidate_r2 / "app.py").read_text(encoding="utf-8") == "print('edited')\n"
