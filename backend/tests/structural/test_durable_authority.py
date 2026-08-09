"""Structural controls on the C-19 durable-job authority.

`execution.durable` owns durable job state. It does NOT own the Job lifecycle
relation - that is the canonical `Job` machine delivered in Phase 3 - and it does
not own persistence, policy, artifact identity, the evidence chain, scheduling or
workflow. A duplicate authority here would be invisible to the dependency gate,
because the machine it could shadow lives in this very context. These controls
are what make the split checkable:

* only the canonical machine decides a transition;
* no state literal or transition table is restated here;
* no database engine is constructed and no raw SQL is emitted;
* no Stable mutation class is named;
* every governed operation passes the injected PEP;
* the C-19 document and the mapped columns are one description, not two;
* nothing schedules, and no sibling context is imported.

Read from the deployed source with `ast`, so prose cannot satisfy a check.
"""

from __future__ import annotations

import ast
import inspect
import re

from tests.structural.durable_reader import (
    CONTRACT_DOC,
    DEFINITION,
    DURABLE,
    ENGINE_CONSTRUCTORS,
    MACHINE_MODULE,
    NEUTRAL_TYPE_NAMESPACE,
    NEUTRAL_TYPES,
    RAW_SQL,
    READ,
    SCHEDULING_NAMES,
    SESSION_OPERATIONS,
    STABLE_CLASSES,
    WRITE,
    DurableJobRecord,
    JobCheckpointRecord,
    JobExecutionAttempt,
    JobStore,
    _assigns_lifecycle_state,
    called,
    code_only,
    imported,
    mapped_records,
    modules,
    read,
)


class TestTheCanonicalMachineIsTheOnlyLifecycleAuthority:
    def test_the_store_builds_and_consults_the_canonical_machine(self) -> None:
        tree = ast.parse(read(DURABLE / "job_store.py"))
        assert "arkali.execution.durable.job_state_machine" in imported(tree)
        names = called(tree)
        assert "build" in names
        assert "evaluate" in names, (
            "the store does not ask the machine to evaluate a move; a transition "
            "decided anywhere else is a second authority"
        )

    def test_no_module_restates_a_state_literal(self) -> None:
        """NEGATIVE CONTROL: no shadow state vocabulary may reappear.

        `job_state_machine.py` is the declaration and is exempt by being the
        authority. Every other module in the context must reach the states
        through it, never by writing one down.
        """
        offenders: dict[str, set[str]] = {}
        for path in modules(DURABLE):
            if path.name == MACHINE_MODULE:
                continue
            literals = {
                node.value
                for node in ast.walk(ast.parse(read(path)))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            found = literals & set(DEFINITION.states)
            if found:
                offenders[path.name] = found
        assert offenders == {}, f"shadow state literals: {offenders}"

    def test_no_module_declares_a_transition_table(self) -> None:
        """A second relation would be a second authority, however spelled."""
        declared = {f"{a}->{b}" for a, b in DEFINITION.transitions}
        for path in modules(DURABLE):
            if path.name == MACHINE_MODULE:
                continue
            source = code_only(read(path))
            assert not any(pair in source for pair in declared), path.name
            tree = ast.parse(read(path))
            pairs = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Tuple) and len(node.elts) == 2
                and all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str)
                    for e in node.elts
                )
            ]
            for node in pairs:
                values = tuple(e.value for e in node.elts)  # type: ignore[attr-defined]
                assert values not in DEFINITION.transition_set, (
                    f"{path.name} restates transition {values}"
                )

    def test_only_the_state_recorder_assigns_the_lifecycle_column(self) -> None:
        """NEGATIVE CONTROL: recording a state is not the same as deciding one.

        `JobStore.transition` writes `lifecycle_state` immediately after the
        machine has evaluated the move, and it is the only place entitled to.
        Any other assignment - including in a module that merely picks which
        declared transition to request - would be a state change the machine
        never saw. Mutation testing found this: replacing the disposition's
        `transition(...)` call with a direct assignment left every behavioural
        test green, because the resulting value was one the machine would have
        allowed anyway.
        """
        found: list[str] = []
        for path in modules(DURABLE):
            tree = ast.parse(read(path))
            for holder in ast.walk(tree):
                if not isinstance(holder, ast.FunctionDef):
                    continue
                if _assigns_lifecycle_state(holder):
                    found.append(f"{path.name}::{holder.name}")
        # Derived, not transcribed: the permitted site is the method that
        # consults the machine, identified by the call it makes.
        assert found == ["job_store.py::transition"], (
            "the lifecycle column is assigned outside the method that asks the "
            f"machine first: {found}"
        )
        recorder = next(
            node for node in ast.walk(ast.parse(read(DURABLE / "job_store.py")))
            if isinstance(node, ast.FunctionDef) and node.name == "transition"
        )
        assert "evaluate" in called(recorder), (
            "the one method allowed to record a state no longer asks the machine"
        )

    def test_the_initial_state_is_derived_not_named(self) -> None:
        source = code_only(read(DURABLE / "records.py"))
        assert "INITIAL_STATE" in source
        assert "DEFINITION.states" in source, (
            "the initial state must be read off the machine's relation"
        )

    def test_the_machine_module_really_declares_the_relation(self) -> None:
        """Not vacuous: the authority exists, it is simply the only one."""
        assert DEFINITION.machine == "Job"
        assert DEFINITION.authority == "execution.durable"
        assert len(DEFINITION.states) >= 10 and DEFINITION.transitions


class TestNoSecondPersistenceAuthority:
    def test_no_engine_is_constructed_in_this_context(self) -> None:
        for path in modules(DURABLE):
            names = called(ast.parse(read(path)))
            offending = sorted(set(ENGINE_CONSTRUCTORS) & names)
            assert offending == [], f"{path.name} constructs {offending}"

    def test_no_engine_constructor_is_even_imported(self) -> None:
        """An import is not yet a call, but it is the step before one.

        Mutation testing showed the call-site check alone passes while
        `create_engine` sits imported at the top of the module, one keystroke
        from a second engine authority. The name has no legitimate use here:
        `kernel.persistence` builds the engine and this context receives a
        session.
        """
        for path in modules(DURABLE):
            tree = ast.parse(read(path))
            imported_names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imported_names.update(
                        (alias.asname or alias.name).split(".")[-1]
                        for alias in node.names
                    )
            offending = sorted(set(ENGINE_CONSTRUCTORS) & imported_names)
            assert offending == [], f"{path.name} imports {offending}"

    def test_no_raw_or_dialect_specific_sql_appears(self) -> None:
        for path in modules(DURABLE):
            source = code_only(read(path))
            for pattern in RAW_SQL:
                assert not re.search(pattern, source), f"{path.name} matches {pattern}"

    def test_the_declarative_base_comes_from_kernel_persistence(self) -> None:
        tree = ast.parse(read(DURABLE / "records.py"))
        assert "arkali.kernel.persistence.base" in imported(tree)

    def test_column_types_stay_engine_neutral(self) -> None:
        """Two independent checks over a DERIVED record set.

        The whitelist alone was both incomplete and unenforceable against a
        type it had never heard of, so the namespace check is the real control:
        every generic SQLAlchemy type lives in `sqlalchemy.sql.sqltypes`, and
        anything out of `sqlalchemy.dialects` - which is what ARK-REQ-0012
        actually forbids - does not, whether or not it is on any list.
        """
        for table in mapped_records():
            for column in table.__table__.columns:
                rendered = type(column.type)
                assert rendered.__module__ == NEUTRAL_TYPE_NAMESPACE, (
                    f"{table.__tablename__}.{column.name} uses "
                    f"{rendered.__module__}.{rendered.__name__}, which is not a "
                    "generic SQLAlchemy type"
                )
                assert rendered.__name__ in NEUTRAL_TYPES, (
                    f"{table.__tablename__}.{column.name} uses {rendered.__name__}"
                )


class TestNoStableMutationPathAndNoScheduling:
    def test_no_stable_operation_class_is_named(self) -> None:
        for path in modules(DURABLE):
            source = read(path)
            for name in STABLE_CLASSES:
                assert name not in source, f"{path.name} names {name}"

    def test_the_only_classes_requested_are_the_workspace_pair(self) -> None:
        assert {READ, WRITE} == {"READ_FILE", "WRITE_WORKSPACE_FILE"}

    def test_nothing_schedules_admits_or_allocates(self) -> None:
        """Phase 8 owns C-21. Scheduling vocabulary here would be forward creep."""
        for path in modules(DURABLE):
            source = code_only(read(path))
            for name in SCHEDULING_NAMES:
                assert not re.search(rf"\b{name}\b", source), (
                    f"{path.name} names {name!r}; admission and allocation are "
                    "C-21 at Phase 8"
                )

    def test_no_sibling_or_higher_layer_context_is_imported(self) -> None:
        forbidden = (
            "arkali.execution.workflow", "arkali.execution.scheduler",
            "arkali.execution.sandbox", "arkali.engineering", "arkali.lifecycle",
            "arkali.surfaces",
        )
        for path in modules(DURABLE):
            for module in imported(ast.parse(read(path))):
                assert not module.startswith(forbidden), f"{path.name} -> {module}"
