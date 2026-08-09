"""Structural controls on C-19 pause, resume and crash recovery (Package 3).

Third module over the shared reader because `module <= 400 logical lines` is a
real architecture budget and ADR-0008 makes decomposition the answer rather than
an exception.

What these establish, over the DEPLOYED SOURCE with `ast`:

* recovery decides that an execution is gone, never who should run it next;
* staleness is computed from PERSISTED facts and the INJECTED clock, with no
  wall-clock source anywhere in the context and nothing that sleeps;
* the sweep composes Package 2's disposition rather than re-deciding it;
* the heartbeat term and the deadline term stay distinct (F-0036);
* the migration chain stayed linear and the new record reached it.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

from tests.structural.durable_reader import (
    DURABLE,
    _assigns_lifecycle_state,
    called,
    code_only,
    mapped_records,
    modules,
    read,
    transition_requests,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
VERSIONS: Final[pathlib.Path] = REPO / "backend" / "alembic" / "versions"
ENV: Final[pathlib.Path] = REPO / "backend" / "alembic" / "env.py"
RECOVERY: Final[pathlib.Path] = DURABLE / "recovery.py"

#: The one place in this context entitled to read a wall clock: the default the
#: injected clock falls back to. Everything else must receive it.
CLOCK_SOURCE: Final[tuple[str, str]] = ("records.py", "utc_now")

#: Names that would mean recovery had started choosing an executor rather than
#: observing that one is gone.
SELECTION_NAMES: Final[tuple[str, ...]] = (
    "select_worker", "choose_owner", "next_owner", "assign", "reassign",
    "rebalance", "pick", "schedule",
)


def _functions(path: pathlib.Path) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.walk(ast.parse(read(path)))
        if isinstance(node, ast.FunctionDef)
    }


def _attributes(node: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


class TestRecoveryUsesPersistedFactsAndAnInjectedClock:
    def test_staleness_is_computed_from_the_persisted_columns(self) -> None:
        """The recovery decision reads the row, not a process-local value.

        NEGATIVE CONTROL for the shape the defect would take: liveness derived
        from something the current process happens to know - a cache, an
        in-memory registry of live workers, a counter - rather than from what
        the database says about the last proof of life.
        """
        stale = _functions(RECOVERY)["_stale"]
        reads = _attributes(stale)
        assert "heartbeat_at" in reads, (
            "the staleness rule does not read the persisted heartbeat"
        )
        assert "heartbeat_timeout_seconds" in reads, (
            "the staleness rule does not read the persisted bound"
        )
        assert "_clock" in reads, "the staleness rule does not use the clock"

    def test_no_module_in_the_context_reads_a_wall_clock(self) -> None:
        """NEGATIVE CONTROL. Exactly one wall-clock source, and it is the
        default the injected clock falls back to.

        Derived: the sweep is over every module, and the single permitted site
        is identified by the function that holds it, so moving the call
        elsewhere fails even if the name is kept.
        """
        offenders: list[str] = []
        for path in modules(DURABLE):
            for name, node in _functions(path).items():
                if (path.name, name) == CLOCK_SOURCE:
                    continue
                names = called(node)
                if names & {"now", "utcnow", "time", "monotonic", "perf_counter"}:
                    offenders.append(f"{path.name}::{name}")
        assert offenders == [], (
            f"{offenders} read a clock directly; time must be injected so "
            "recovery is deterministic"
        )
        permitted = _functions(DURABLE / CLOCK_SOURCE[0])[CLOCK_SOURCE[1]]
        assert "now" in called(permitted), (
            "the permitted clock source no longer reads a clock; this control "
            "would be exempting nothing"
        )

    def test_nothing_in_the_context_sleeps_or_polls(self) -> None:
        for path in modules(DURABLE):
            source = code_only(read(path))
            for shape in (r"\bsleep\b", r"\bwait\b", r"\bpoll\b", r"\bretry_until\b"):
                assert not re.search(shape, source), f"{path.name} matches {shape}"

    def test_the_clock_is_injected_into_every_service(self) -> None:
        import inspect

        from arkali.execution.durable.job_type import JobTypeRegistry
        from arkali.execution.durable.recovery import JobRecovery

        for service in (JobRecovery, JobTypeRegistry):
            parameters = inspect.signature(service.__init__).parameters
            assert "clock" in parameters, f"{service.__name__} takes no clock"
            assert parameters["pep"].default is inspect.Parameter.empty, (
                f"{service.__name__} would write without a policy decision"
            )


class TestRecoveryIsNotScheduling:
    def test_the_sweep_does_not_start_the_next_attempt(self) -> None:
        """The durability/scheduling boundary, stated structurally.

        Leaving a recovered job in `RESUMING` is the boundary: opening the next
        attempt would mean deciding that someone should run it now, and
        choosing who is `execution.scheduler` at Phase 8.
        """
        names = called(_functions(RECOVERY)["recover_lost_executions"])
        assert "begin_attempt" not in names, (
            "the sweep starts the next attempt; recovery stops at RESUMING"
        )

    def test_no_owner_selection_vocabulary_appears(self) -> None:
        for path in modules(DURABLE):
            source = code_only(read(path))
            for name in SELECTION_NAMES:
                assert not re.search(rf"\b{name}\b", source), (
                    f"{path.name} names {name!r}; recovery observes that an "
                    "owner is gone and never chooses the next one"
                )

    def test_recovery_reuses_the_recorded_owner_and_invents_none(self) -> None:
        """The owner passed to the failure path comes off the attempt row."""
        source = code_only(read(RECOVERY))
        assert "attempt.owner" in source, (
            "the sweep does not act on the recorded owner"
        )

    def test_the_sweep_composes_the_package_2_disposition(self) -> None:
        """It must not re-decide retry versus dead-letter.

        NEGATIVE CONTROL for a second copy of the retry policy: the sweep calls
        the failure path and READS what it chose. If it named `DEAD_LETTER` or
        consulted the bound itself, the disposition would exist twice and the
        two copies could disagree.
        """
        sweep = _functions(RECOVERY)["recover_lost_executions"]
        names = called(sweep)
        assert "fail_attempt" in names, "the sweep does not use the failure path"
        assert "retry_permitted" not in names, (
            "the sweep re-decides the disposition Package 2 owns"
        )
        source = code_only(read(RECOVERY))
        assert "DEAD_LETTER" not in source, (
            "recovery.py names DEAD_LETTER; the disposition belongs to "
            "execution.py and reading its outcome is enough"
        )


class TestTheHeartbeatTermStaysDistinctFromTheDeadline:
    """F-0036, as a permanent control rather than a repaired name.

    Package 2 shipped `heartbeat_expired`, which resolved to a comparison
    against `deadline_at` and never read `heartbeat_at` at all. The name
    promised silence and the behaviour measured elapsed work. Consumed as
    written by Package 3's canonical crash-recovery rule, it would have
    recovered live workers and left dead ones holding their jobs.
    """

    def test_a_function_named_for_the_heartbeat_must_read_the_heartbeat(
        self,
    ) -> None:
        """Derived over the whole context, so the next such name is covered.

        Private helpers are resolved one level: a function whose body only
        delegates satisfies this through the helper it calls.
        """
        for path in modules(DURABLE):
            functions = _functions(path)
            for name, node in functions.items():
                if "heartbeat" not in name:
                    continue
                reads = set(_attributes(node))
                for called_name in called(node):
                    if called_name in functions:
                        reads |= _attributes(functions[called_name])
                assert "heartbeat_at" in reads, (
                    f"{path.name}::{name} is named for the heartbeat but never "
                    "reads heartbeat_at - the F-0036 shape"
                )

    def test_a_function_named_for_the_deadline_or_timeout_reads_the_deadline(
        self,
    ) -> None:
        """The mirror direction, so the repair cannot swing the other way."""
        functions = _functions(DURABLE / "execution.py")
        timed_out = functions["timed_out"]
        reads = set(_attributes(timed_out))
        for called_name in called(timed_out):
            if called_name in functions:
                reads |= _attributes(functions[called_name])
        assert "deadline_at" in reads
        assert "heartbeat_at" not in reads, (
            "the timeout rule reads the heartbeat; they are different questions"
        )

    def test_the_two_bounds_are_separate_persisted_columns(self) -> None:
        job = next(
            table for table in mapped_records()
            if table.__tablename__ == "durable_job"
        )
        columns = {c.name for c in job.__table__.columns}
        assert {"attempt_timeout_seconds", "heartbeat_timeout_seconds"} <= columns
        assert job.__table__.columns["heartbeat_timeout_seconds"].nullable is False

    def test_the_old_conflated_name_is_gone(self) -> None:
        """NEGATIVE CONTROL: the repaired name must not come back."""
        for path in modules(DURABLE):
            assert "heartbeat_expired" not in read(path), (
                f"{path.name} reintroduces the F-0036 name"
            )


class TestPauseAndRecoveryShareOneEntryPoint:
    def test_pause_reads_the_registry_and_the_machine_decides_the_move(
        self,
    ) -> None:
        """Both conditions, and neither substitutes for the other."""
        functions = _functions(RECOVERY)
        guard = called(functions["_require_pausable"])
        assert "supports_pause" in guard, (
            "the pause guard does not consult the job-type registry"
        )
        for entry in ("pause", "resume"):
            assert "_require_pausable" in called(functions[entry]), (
                f"{entry} does not check the applicability rule"
            )
        requests = transition_requests(RECOVERY)
        assert requests["pause"] == {"PAUSED"}
        assert requests["resume"] == {"RESUMING", "RUNNING"}, (
            "resume must pass through RESUMING as a real state, not skip it"
        )

    def test_no_module_assigns_a_lifecycle_state_in_this_package(self) -> None:
        """NEGATIVE CONTROL, stated again for the Package 3 modules.

        The context-wide control lives in `test_durable_authority.py`; this one
        fails with a Package 3 message so a direct write here is not diagnosed
        as a Package 2 regression.

        The check is the AST one, not a substring: `recovery.py` legitimately
        COMPARES `lifecycle_state` in the sweep's query filter, and a text
        search cannot tell that from writing to it. Reading where a job is in
        order to decide which rows to consider is not deciding where it goes.
        """
        for path in (RECOVERY, DURABLE / "job_type.py"):
            writers = [
                name for name, node in _functions(path).items()
                if _assigns_lifecycle_state(node)
            ]
            assert writers == [], (
                f"{path.name}::{writers} writes a lifecycle state directly "
                "instead of asking the machine"
            )

    def test_that_control_can_tell_a_comparison_from_an_assignment(self) -> None:
        """Non-vacuity: the sweep really does mention the column it must not
        write, so the control above is passing because of the AST and not
        because the name is absent."""
        assert "lifecycle_state" in code_only(read(RECOVERY)), (
            "the sweep no longer filters on the lifecycle column; the control "
            "above would now pass for the wrong reason"
        )
        mutated = ast.parse(
            "def f(record):\n    record.lifecycle_state = 'RESUMING'\n"
        )
        injected = next(
            node for node in ast.walk(mutated) if isinstance(node, ast.FunctionDef)
        )
        assert _assigns_lifecycle_state(injected) is True, (
            "the detector does not recognise a direct assignment at all"
        )


class TestTheMigrationChainStayedLinear:
    def _revisions(self) -> dict[str, str | None]:
        chain: dict[str, str | None] = {}
        for path in sorted(VERSIONS.glob("*.py")):
            text = read(path)
            revision = re.search(r"^revision[^=\n]*=\s*['\"]([^'\"]+)", text, re.M)
            parent = re.search(
                r"^down_revision[^=\n]*=\s*(?:['\"]([^'\"]+)['\"]|None)", text, re.M
            )
            assert revision is not None, f"{path.name} declares no revision"
            chain[revision.group(1)] = parent.group(1) if parent and parent.group(
                1
            ) else None
        return chain

    def test_there_is_exactly_one_head(self) -> None:
        """Derived from the files, never transcribed - the F-0032 lesson."""
        chain = self._revisions()
        parents = {value for value in chain.values() if value}
        heads = sorted(set(chain) - parents)
        assert len(heads) == 1, f"the chain forked: heads {heads}"
        roots = sorted(name for name, parent in chain.items() if parent is None)
        assert len(roots) == 1, f"the chain has {len(roots)} roots"

    def test_every_revision_is_forward_only(self) -> None:
        for path in sorted(VERSIONS.glob("*.py")):
            assert 'direction: str = "FORWARD"' in read(path), path.name

    def test_every_mapped_table_reaches_a_migration(self) -> None:
        """F-0033's property, stated for the tables rather than the modules.

        The module list in `env.py` is checked by the persistence tier; this
        asks the complementary question - that a record which IS mapped also
        has a migration that creates its table, so a record cannot be added to
        the ORM and silently never exist in a migrated database.
        """
        created = " ".join(read(path) for path in sorted(VERSIONS.glob("*.py")))
        for table in mapped_records():
            assert f'"{table.__tablename__}"' in created, (
                f"{table.__tablename__} is mapped but no migration creates it"
            )

    def test_the_record_module_is_declared_at_the_composition_root(self) -> None:
        text = read(ENV)
        assert "arkali.execution.durable.records" in text
        assert "MAPPED_RECORD_MODULES" in text
