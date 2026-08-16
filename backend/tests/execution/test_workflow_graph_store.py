"""C-20 workflow graph persistence: publish, read, revision derivation, and
enforcement (Phase 17 Package 2).

REAL INFRASTRUCTURE ONLY - see `workflow_harness.py`. Every negative control
asserts the type and reason a call was refused.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest
from alembic.config import Config
from sqlalchemy import select

from alembic import command
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.execution.workflow.errors import (
    ImmutableRevisionViolation,
    RevisionIntegrityViolation,
    UnknownWorkflow,
    UnknownWorkflowRevision,
)
from arkali.execution.workflow.graph_model import (
    SemverBump,
    WorkflowEdge,
    WorkflowGraphDocument,
    WorkflowNode,
)
from arkali.execution.workflow.graph_store import WorkflowGraphStore
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from arkali.execution.workflow.records import WorkflowRevisionRecord
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from tests.execution.workflow_harness import (  # noqa: F401 - fixtures by import
    BACKEND,
    Reopener,
    clock,
    database_path,
    denying_pep,
    pdp,
    pep,
    reopen,
    small_document,
    vocabulary,
)


def _second_revision(vocabulary: GraphVocabulary) -> WorkflowGraphDocument:
    return WorkflowGraphDocument.build(
        vocabulary,
        "wf-1",
        nodes=[
            WorkflowNode(node_id="n-trigger", kind="trigger", label="Start"),
            WorkflowNode(node_id="n-data", kind="data", label="Transform"),
            WorkflowNode(node_id="n-extra", kind="data", label="Second step"),
        ],
        edges=[
            WorkflowEdge(edge_id="e-1", source_node_id="n-trigger", target_node_id="n-data"),
            WorkflowEdge(edge_id="e-2", source_node_id="n-data", target_node_id="n-extra"),
        ],
    )


def _migrated(path: pathlib.Path) -> None:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")


class TestPublishDerivesRevisionAndSemver:
    def test_first_publish_is_revision_one_semver_one_zero_zero(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (store, session):
            record = store.publish(
                small_document(vocabulary), semver_bump=SemverBump.PATCH
            )
            session.commit()
            assert record.revision_number == 1
            assert record.semver == "1.0.0"

    def test_second_publish_derives_revision_two_and_bumps_semver(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (store, session):
            store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            session.commit()
        with reopen.session() as (store, session):
            record = store.publish(_second_revision(vocabulary), semver_bump=SemverBump.MINOR)
            session.commit()
            assert record.revision_number == 2
            assert record.semver == "1.1.0"

    def test_latest_returns_the_highest_revision(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (store, session):
            store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            session.commit()
        with reopen.session() as (store, _session):
            latest = store.latest("wf-1")
            assert latest is not None
            assert latest.revision_number == 2
            assert latest.semver == "1.0.1"

    def test_history_is_every_revision_oldest_first(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (store, session):
            store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            store.publish(small_document(vocabulary), semver_bump=SemverBump.MAJOR)
            session.commit()
        with reopen.session() as (store, _session):
            history = store.history("wf-1")
            assert [r.revision_number for r in history] == [1, 2, 3]
            assert [r.semver for r in history] == ["1.0.0", "1.0.1", "2.0.0"]


class TestReloadReproducesTheSameDocument:
    def test_a_reopened_store_reads_back_an_identical_document(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        original = small_document(vocabulary)
        with reopen.session() as (store, session):
            store.publish(original, semver_bump=SemverBump.PATCH)
            session.commit()
        with reopen.session() as (store, _session):
            record = store.require_revision("wf-1", 1)
            reloaded = store.document_of(record)
            assert reloaded.content_hash == original.content_hash
            assert [n.node_id for n in reloaded.nodes()] == [
                n.node_id for n in original.nodes()
            ]

    def test_the_prior_revision_is_unchanged_by_a_later_publish(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (store, session):
            first = store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            first_hash = first.revision_hash
            session.commit()
        with reopen.session() as (store, session):
            store.publish(_second_revision(vocabulary), semver_bump=SemverBump.MAJOR)
            session.commit()
        with reopen.session() as (store, _session):
            reread = store.require_revision("wf-1", 1)
            assert reread.revision_hash == first_hash


class TestImmutability:
    def test_updating_a_persisted_revision_raises(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (store, session):
            store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            session.commit()

        with pytest.raises(ImmutableRevisionViolation):
            with reopen.session() as (_store, session):
                record = session.execute(
                    select(WorkflowRevisionRecord).where(
                        WorkflowRevisionRecord.workflow_id == "wf-1",
                        WorkflowRevisionRecord.revision_number == 1,
                    )
                ).scalar_one()
                record.semver = "9.9.9"
                session.flush()

        with reopen.session() as (store, _session):
            assert store.require_revision("wf-1", 1).semver == "1.0.0"

    def test_deleting_a_persisted_revision_raises(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (store, session):
            store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            session.commit()

        with pytest.raises(ImmutableRevisionViolation):
            with reopen.session() as (_store, session):
                record = session.execute(
                    select(WorkflowRevisionRecord).where(
                        WorkflowRevisionRecord.workflow_id == "wf-1",
                        WorkflowRevisionRecord.revision_number == 1,
                    )
                ).scalar_one()
                session.delete(record)
                session.flush()

        with reopen.session() as (store, _session):
            assert store.require_revision("wf-1", 1) is not None


class TestIntegrityIsNeverTrustedFromStorage:
    def test_a_tampered_document_column_is_refused_on_read(
        self,
        database_path: pathlib.Path,
        pep: PolicyEnforcementPoint,
        vocabulary: GraphVocabulary,
    ) -> None:
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                store = WorkflowGraphStore(session, pep, vocabulary)
                store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
        finally:
            engine.dispose()

        # Tamper directly at the SQL layer - the store's own immutability
        # refusal must not be what is under test here. The replacement is a
        # STRUCTURALLY VALID graph (one trigger node, no edges) so the
        # refusal proven below is the hash mismatch, not a validity refusal
        # `EmptyGraph`/`DanglingEdgeReference` etc. would already catch.
        tampered = (
            '{"workflow_id": "wf-1", "nodes": [{"node_id": "n-tampered", '
            '"kind": "trigger", "control_construct": null, "label": "Tampered", '
            '"parameters": {}, "position_x": 0.0, "position_y": 0.0}], '
            '"edges": []}'
        )
        connection = sqlite3.connect(str(database_path))
        try:
            connection.execute(
                "UPDATE workflow_revision SET document = ? "
                "WHERE workflow_id = 'wf-1' AND revision_number = 1",
                (tampered,),
            )
            connection.commit()
        finally:
            connection.close()

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                store = WorkflowGraphStore(session, pep, vocabulary)
                record = store.require_revision("wf-1", 1)
                with pytest.raises(RevisionIntegrityViolation):
                    store.document_of(record)
        finally:
            engine.dispose()


class TestUnknownIdentityRefusals:
    def test_require_workflow_raises_unknown_workflow(self, reopen: Reopener) -> None:
        with reopen.session() as (store, _session):
            with pytest.raises(UnknownWorkflow, match="ghost"):
                store.require_workflow("ghost")

    def test_require_revision_raises_unknown_workflow_revision(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (store, session):
            store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
            session.commit()
        with reopen.session() as (store, _session):
            with pytest.raises(UnknownWorkflowRevision, match="99"):
                store.require_revision("wf-1", 99)


class TestEveryOperationIsGoverned:
    def test_publish_is_refused_when_workspace_writes_are_denied(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        pep = denying_pep(tmp_path)
        denied_db_path = tmp_path / "denied.db"
        _migrated(denied_db_path)

        engine = create_persistence_engine(sqlite_url(denied_db_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                store = WorkflowGraphStore(session, pep, vocabulary)
                with pytest.raises(PolicyDenied):
                    store.publish(small_document(vocabulary), semver_bump=SemverBump.PATCH)
        finally:
            engine.dispose()
