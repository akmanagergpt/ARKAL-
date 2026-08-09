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
import pathlib
import re
from typing import Final

from arkali.execution.durable.job_state_machine import DEFINITION
from arkali.execution.durable.job_store import READ, WRITE, JobStore
from arkali.execution.durable.records import (
    DurableJobRecord,
    JobCheckpointRecord,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE: Final[pathlib.Path] = REPO / "backend" / "arkali"
DURABLE: Final[pathlib.Path] = PACKAGE / "execution" / "durable"
MACHINE_MODULE: Final[str] = "job_state_machine.py"
CONTRACT_DOC: Final[pathlib.Path] = REPO / "docs" / "contracts" / "job.md"

#: Names that would mean this context had started building its own engine.
ENGINE_CONSTRUCTORS: Final[tuple[str, ...]] = (
    "create_engine", "create_async_engine", "sessionmaker",
    "async_sessionmaker", "declarative_base",
)
#: Anything that would mean raw or dialect-specific SQL had appeared.
RAW_SQL: Final[tuple[str, ...]] = (
    r"\btext\s*\(", r"\bexecute\s*\(\s*[\"']", r"\bPRAGMA\b", r"\bsqlite3\b",
    r"\bpsycopg", r"sqlalchemy\.dialects",
)
#: The two operation classes this context must never name (structure check 11).
STABLE_CLASSES: Final[tuple[str, ...]] = ("WRITE_STABLE_FILE", "ROLLBACK_STABLE")
#: Phase 8 vocabulary. Present here would mean scheduling had leaked forward.
SCHEDULING_NAMES: Final[tuple[str, ...]] = (
    "admit", "admission", "claim", "lease", "dequeue", "enqueue_to_worker",
    "worker_pool", "resource_budget", "allocate",
)


def modules(root: pathlib.Path) -> list[pathlib.Path]:
    found = sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")
    assert found, f"no module under {root}; this control would be vacuous"
    return found


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """Source with docstrings and comments removed."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                text = text.replace(doc, "")
    return re.sub(r"#[^\n]*", "", text)


def called(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def imported(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


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
        for table in (DurableJobRecord, JobCheckpointRecord):
            for column in table.__table__.columns:
                rendered = type(column.type).__name__
                assert rendered in {"String", "Integer", "DateTime", "JSON"}, (
                    f"{table.__tablename__}.{column.name} uses {rendered}"
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


class TestEveryGovernedOperationIsGuarded:
    def test_the_pep_is_injected_with_no_default(self) -> None:
        import inspect

        signature = inspect.signature(JobStore.__init__)
        assert signature.parameters["pep"].default is inspect.Parameter.empty, (
            "a default PEP would let a caller obtain a store that writes "
            "without a policy decision"
        )

    def test_every_public_method_that_touches_the_session_guards_first(self) -> None:
        """AST: a method reaching the session must call `_guard`.

        NEGATIVE CONTROL for the shape an unguarded operation would take. The
        subject is derived from the source, so a method added later is covered
        without editing this control.
        """
        tree = ast.parse(read(DURABLE / "job_store.py"))
        store = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "JobStore"
        )
        checked = 0
        for method in store.body:
            if not isinstance(method, ast.FunctionDef) or method.name.startswith("_"):
                continue
            body = ast.dump(method)
            touches_session = "_session" in body
            if not touches_session:
                continue
            checked += 1
            guards = "_guard" in called(method)
            delegates = any(
                name in called(method)
                for name in ("get", "require", "find_submitted",
                             "next_checkpoint_sequence", "checkpoints")
            )
            assert guards or delegates, (
                f"JobStore.{method.name} touches the session without a policy "
                "decision and without delegating to a method that takes one"
            )
        assert checked >= 5, "the sweep found too few session-touching methods"

    def test_the_write_path_requests_the_workspace_class(self) -> None:
        source = code_only(read(DURABLE / "job_store.py"))
        assert "_guard(WRITE)" in source
        assert "_guard(READ)" in source


class TestContractAndSchemaAgree:
    def test_the_contract_document_exists_and_names_the_owner(self) -> None:
        text = read(CONTRACT_DOC)
        assert "C-19" in text
        assert "`execution.durable`" in text
        assert "**Phase:** 7" in text

    def test_every_mapped_column_is_documented(self) -> None:
        text = read(CONTRACT_DOC)
        for table in (DurableJobRecord, JobCheckpointRecord):
            assert table.__tablename__ in text
            for column in table.__table__.columns:
                assert f"`{column.name}`" in text, (
                    f"{table.__tablename__}.{column.name} is mapped but undocumented"
                )

    def test_the_document_declares_no_column_the_schema_lacks(self) -> None:
        """Both directions, so the document cannot promise a field that is absent.

        Only the record ROWS of section 4 are read, not its prose: the prose
        legitimately names ORM events and constraints, which are not columns.
        """
        for table in (DurableJobRecord, JobCheckpointRecord):
            mapped = {column.name for column in table.__table__.columns}
            row = next(
                line for line in read(CONTRACT_DOC).splitlines()
                if line.startswith(f"| `{table.__tablename__}` |")
            )
            fields = row.split("|")[2]
            documented = set(re.findall(r"`([a-z_]+)`", fields)) - {
                table.__tablename__, "durable_job", "job_checkpoint",
            }
            assert documented == mapped, (
                f"{table.__tablename__}: documented {sorted(documented)} but "
                f"mapped {sorted(mapped)}"
            )

    def test_the_document_states_what_the_contract_does_not_own(self) -> None:
        text = read(CONTRACT_DOC)
        for boundary in ("C-21", "C-20", "C-14", "C-15", "ARK-REQ-0327"):
            assert boundary in text, f"the document does not disclaim {boundary}"
