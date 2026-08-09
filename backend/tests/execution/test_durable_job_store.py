"""C-19 durable job persistence on real infrastructure.

Phase 7 Atomic Package 1. A real SQLite file migrated by the real Alembic chain,
a real PDP loaded from the authority map, and a real PEP. Nothing is substituted;
`VERIFICATION_ARCHITECTURE.md` section 1.1 forbids it from T5 upward.

Every "reopen" disposes the engine and builds a NEW one over the SAME file, so a
value read afterwards came off the disk and not out of an identity map.

Scope note: this package discharges NO Phase 7 requirement. ARK-REQ-0003, 0027,
0059, 0060 and 0061 remain open; discharge belongs to the Phase 7 traceability
record, report and gate.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import shutil
from collections.abc import Iterator

import pytest
import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, select

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.execution.durable.errors import (
    CheckpointImmutabilityViolation,
    DuplicateJobIdentity,
    InvalidJobIdentity,
    UnknownJob,
)
from arkali.execution.durable.job_state_machine import DEFINITION
from arkali.execution.durable.job_store import ACTOR, JobStore, JobSubmission
from arkali.execution.durable.records import (
    INITIAL_STATE,
    DurableJobRecord,
    JobCheckpointRecord,
)
from arkali.kernel.contracts.state_machine_errors import (
    IllegalTransition,
    TerminalStateEscape,
    UnknownState,
)
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

#: A fixed instant, so a recorded timestamp is an asserted value rather than
#: whatever the wall clock happened to say. The clock is injected precisely so
#: no test needs to sleep.
FROZEN = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)


def frozen_clock() -> dt.datetime:
    return FROZEN


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "execution.durable.job_store")


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "durable.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


class Reopener:
    """Opens a store over one database file, with a new engine every time."""

    def __init__(self, path: pathlib.Path, pep: PolicyEnforcementPoint) -> None:
        self._path = path
        self._pep = pep
        self.opens = 0

    def session(self):  # noqa: ANN201 - a context manager
        self.opens += 1
        engine = create_persistence_engine(sqlite_url(self._path))
        factory = create_session_factory(engine)
        uow = unit_of_work(factory)

        class _Scope:
            def __enter__(inner) -> tuple[JobStore, object]:  # noqa: N805
                session = uow.__enter__()
                return JobStore(session, self._pep, frozen_clock), session

            def __exit__(inner, *exc: object) -> bool:  # noqa: N805
                try:
                    return bool(uow.__exit__(*exc))
                finally:
                    engine.dispose()

        return _Scope()


@pytest.fixture()
def reopen(database_path: pathlib.Path, pep: PolicyEnforcementPoint) -> Reopener:
    return Reopener(database_path, pep)


def submission(**overrides: object) -> JobSubmission:
    fields: dict[str, object] = {
        "job_id": "JOB-0001",
        "job_type": "arkali.test.noop",
        "idempotency_key": "key-1",
        "payload": {"input": 1},
    }
    fields.update(overrides)
    return JobSubmission(**fields)  # type: ignore[arg-type]


# -- identity and idempotency -------------------------------------------------


class TestIdentity:
    def test_a_submitted_job_starts_in_the_machines_initial_state(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            record = store.submit(submission())
        assert record.lifecycle_state == INITIAL_STATE
        # Derived, not named: the one state with no incoming transition.
        assert INITIAL_STATE in DEFINITION.states
        assert all(target != INITIAL_STATE for _, target in DEFINITION.transitions)

    def test_job_identity_is_unique(self, reopen: Reopener) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            with pytest.raises(DuplicateJobIdentity):
                store.submit(submission(idempotency_key="key-2"))

    def test_an_empty_identity_is_refused(self, reopen: Reopener) -> None:
        with reopen.session() as (store, _):
            for field in ("job_id", "job_type", "idempotency_key"):
                with pytest.raises(InvalidJobIdentity):
                    store.submit(submission(**{field: "   "}))

    def test_an_unknown_job_is_refused_by_type(self, reopen: Reopener) -> None:
        with reopen.session() as (store, _):
            with pytest.raises(UnknownJob):
                store.require("JOB-absent")

    def test_the_same_key_under_a_different_type_is_a_different_job(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            first = store.submit(submission())
            second = store.submit(
                submission(job_id="JOB-0002", job_type="arkali.test.other")
            )
        assert first.job_id != second.job_id


class TestIdempotencyIsPersisted:
    def test_a_repeated_key_returns_the_same_job_after_reopen(
        self, reopen: Reopener
    ) -> None:
        """The proof the requirement asks for: no second logical job, ever."""
        with reopen.session() as (store, _):
            original = store.submit(submission())
            original_id = original.job_id

        # A completely new engine and session; an in-memory cache would be gone.
        with reopen.session() as (store, session):
            again = store.submit(submission(job_id="JOB-DIFFERENT"))
            assert again.job_id == original_id
            rows = session.execute(select(DurableJobRecord)).scalars().all()
            assert len(rows) == 1, "a duplicate submission created a second job"

        assert reopen.opens == 2

    def test_the_guarantee_is_the_constraint_not_the_lookup(
        self, reopen: Reopener
    ) -> None:
        """Bypassing `submit` still cannot produce a second identity.

        A caller that writes the record directly - the shape a second submission
        path would take - is refused by the database, so the invariant does not
        depend on everyone using the service.
        """
        from sqlalchemy.exc import IntegrityError

        with reopen.session() as (store, _):
            store.submit(submission())

        with pytest.raises(IntegrityError):
            with reopen.session() as (_store, session):
                session.add(
                    DurableJobRecord(
                        job_id="JOB-SNEAK",
                        job_type="arkali.test.noop",
                        idempotency_key="key-1",
                        lifecycle_state=INITIAL_STATE,
                        payload={},
                        created_at=FROZEN,
                        updated_at=FROZEN,
                    )
                )
                session.flush()

        with reopen.session() as (_store, session):
            rows = session.execute(select(DurableJobRecord)).scalars().all()
            assert [r.job_id for r in rows] == ["JOB-0001"]

    def test_a_repeated_submission_does_not_overwrite_the_recorded_job(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            store.transition("JOB-0001", "RUNNING")

        with reopen.session() as (store, _):
            again = store.submit(submission(payload={"input": 999}))
            assert again.lifecycle_state == "RUNNING"
            assert again.payload == {"input": 1}


# -- durability ---------------------------------------------------------------


class TestDurability:
    def test_job_state_survives_engine_disposal_and_reconstruction(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            store.transition("JOB-0001", "RUNNING")

        with reopen.session() as (store, _):
            record = store.require("JOB-0001")
            assert record.lifecycle_state == "RUNNING"
            assert record.payload == {"input": 1}
            assert record.created_at is not None

    def test_checkpoints_survive_engine_disposal_and_reconstruction(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            store.checkpoint("JOB-0001", {"offset": 10})
            store.checkpoint("JOB-0001", {"offset": 20})

        with reopen.session() as (store, _):
            stored = store.checkpoints("JOB-0001")
            assert [c.sequence for c in stored] == [1, 2]
            assert [c.payload["offset"] for c in stored] == [10, 20]

    def test_checkpoint_ordering_cannot_silently_collide(
        self, reopen: Reopener
    ) -> None:
        """The ordinal is part of the primary key, so a reuse is refused."""
        from sqlalchemy.exc import IntegrityError

        with reopen.session() as (store, _):
            store.submit(submission())
            store.checkpoint("JOB-0001", {"offset": 1})

        with pytest.raises(IntegrityError):
            with reopen.session() as (_store, session):
                session.add(
                    JobCheckpointRecord(
                        job_id="JOB-0001", sequence=1, payload={"offset": 2},
                        recorded_at=FROZEN,
                    )
                )
                session.flush()

    def test_a_checkpoint_cannot_reference_a_job_that_was_never_submitted(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            with pytest.raises(UnknownJob):
                store.checkpoint("JOB-absent", {"offset": 1})

    def test_a_persisted_checkpoint_cannot_be_modified_or_deleted(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            store.checkpoint("JOB-0001", {"offset": 1})

        with pytest.raises(CheckpointImmutabilityViolation):
            with reopen.session() as (store, session):
                store.checkpoints("JOB-0001")[0].payload = {"offset": 99}
                session.flush()

        with pytest.raises(CheckpointImmutabilityViolation):
            with reopen.session() as (store, session):
                session.delete(store.checkpoints("JOB-0001")[0])
                session.flush()

        with reopen.session() as (store, _):
            assert store.checkpoints("JOB-0001")[0].payload == {"offset": 1}

    def test_a_failed_transaction_persists_no_partial_state(
        self, reopen: Reopener
    ) -> None:
        """The unit of work rolls back; a half-written job must not survive."""
        with pytest.raises(RuntimeError):
            with reopen.session() as (store, _):
                store.submit(submission())
                store.checkpoint("JOB-0001", {"offset": 1})
                raise RuntimeError("the caller's work failed after writing")

        with reopen.session() as (store, session):
            assert store.get("JOB-0001") is None
            assert session.execute(select(JobCheckpointRecord)).scalars().all() == []


# -- lifecycle delegation -----------------------------------------------------


class TestLifecycleIsDelegated:
    def test_a_legal_move_is_recorded(self, reopen: Reopener) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            outcome = store.transition("JOB-0001", "RUNNING")
            assert outcome.machine == "Job"
            assert outcome.source == INITIAL_STATE
            assert outcome.target == "RUNNING"

    def test_the_store_defers_to_the_canonical_machine(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            assert store.machine_name == DEFINITION.machine

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            ("SUCCEEDED", IllegalTransition),   # QUEUED -> SUCCEEDED is undeclared
            ("NOT_A_STATE", UnknownState),
        ],
    )
    def test_an_illegal_move_is_refused_by_the_machine(
        self, reopen: Reopener, target: str, expected: type[Exception]
    ) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            with pytest.raises(expected):
                store.transition("JOB-0001", target)

    def test_a_terminal_job_cannot_move_again(self, reopen: Reopener) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            store.transition("JOB-0001", "RUNNING")
            store.transition("JOB-0001", "SUCCEEDED")
            with pytest.raises(TerminalStateEscape):
                store.transition("JOB-0001", "RUNNING")

    def test_a_refused_move_leaves_the_recorded_state_unchanged(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            with pytest.raises(IllegalTransition):
                store.transition("JOB-0001", "SUCCEEDED")

        with reopen.session() as (store, _):
            assert store.require("JOB-0001").lifecycle_state == INITIAL_STATE


# -- policy -------------------------------------------------------------------


class TestPolicyEnforcement:
    def test_every_operation_is_audited_through_the_phase_4_pep(
        self, reopen: Reopener, pep: PolicyEnforcementPoint
    ) -> None:
        with reopen.session() as (store, _):
            store.submit(submission())
            store.transition("JOB-0001", "RUNNING")
            store.checkpoint("JOB-0001", {"offset": 1})
            store.checkpoints("JOB-0001")

        trail = pep.audit_trail
        assert trail
        assert {record.actor for record in trail} == {ACTOR}
        assert {record.operation_class for record in trail} == {
            "READ_FILE", "WRITE_WORKSPACE_FILE"
        }

    def test_a_denied_decision_prevents_the_write(
        self, tmp_path: pathlib.Path, database_path: pathlib.Path
    ) -> None:
        """A REAL PDP, loaded from a controlled authority map that denies.

        The PEP is the shipping one and the PDP is the shipping one; only the
        governed data it reads is a fixture, so this proves a real refusal rather
        than proving that a stand-in object can raise.
        """
        root = tmp_path / "denying_repo"
        for relative in ("docs/canonical/AUTHORITY_MAP.yaml",
                         "docs/canonical/SECURITY_ARCHITECTURE.md",
                         "docs/canonical/ARCHITECTURE.md"):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        mapping = yaml.safe_load(
            (root / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
        )
        mapping["operation_classes"]["WRITE_WORKSPACE_FILE"] = {
            "default": "DENY", "fixed": "DENY"
        }
        (root / "docs/canonical/AUTHORITY_MAP.yaml").write_text(
            yaml.safe_dump(mapping), encoding="utf-8"
        )
        denying = PolicyEnforcementPoint(PolicyDecisionPoint.load(root), "denied")

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with pytest.raises(PolicyDenied):
                with unit_of_work(create_session_factory(engine)) as session:
                    JobStore(session, denying, frozen_clock).submit(submission())
        finally:
            engine.dispose()

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                assert session.execute(select(DurableJobRecord)).scalars().all() == []
        finally:
            engine.dispose()

    def test_the_real_pdp_denies_a_stable_write_to_this_actor(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """NEGATIVE CONTROL: DENY is a hard refusal for this actor too."""
        from arkali.control.policy.policy_contract import PolicyRequest

        probe = PolicyEnforcementPoint(pdp, "probe")
        for operation in ("WRITE_STABLE_FILE", "ROLLBACK_STABLE"):
            with pytest.raises(PolicyDenied):
                probe.enforce(
                    PolicyRequest(
                        operation_class=operation, trust_tier="TRUST-0", actor=ACTOR
                    )
                )


class TestInjectedClock:
    def test_recorded_timestamps_come_from_the_injected_clock(
        self, engine: Engine, pep: PolicyEnforcementPoint
    ) -> None:
        """No test sleeps, because nothing reads the wall clock."""
        with unit_of_work(create_session_factory(engine)) as session:
            store = JobStore(session, pep, frozen_clock)
            record = store.submit(submission())
            checkpoint = store.checkpoint("JOB-0001", {"offset": 1})
            assert record.created_at == FROZEN
            assert record.updated_at == FROZEN
            assert checkpoint.recorded_at == FROZEN
