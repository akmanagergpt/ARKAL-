"""C-19 governed-operation and contract controls for `execution.durable`.

Second half of the authority controls, over the shared reader. Two modules
because `module <= 400 logical lines` is a real budget and ADR-0008 makes
decomposition the answer rather than an exception.
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
    modules,
    read,
)


class TestEveryGovernedOperationIsGuarded:
    def test_the_pep_is_injected_with_no_default(self) -> None:
        import inspect

        signature = inspect.signature(JobStore.__init__)
        assert signature.parameters["pep"].default is inspect.Parameter.empty, (
            "a default PEP would let a caller obtain a store that writes "
            "without a policy decision"
        )

    def test_every_session_touching_method_guards_first(self) -> None:
        """AST: any method reaching the session must take a policy decision.

        NEGATIVE CONTROL for the shape an unguarded operation would take. The
        subject is derived from the source - every class in every module of the
        context, private methods included - so a method or a whole service added
        later is covered without editing this control. Package 2's `_close`
        writes through the session from a private method, which an earlier
        public-only sweep did not see.
        """
        checked = 0
        for path in modules(DURABLE):
            tree = ast.parse(read(path))
            for klass in [
                n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
            ]:
                # Methods that delegate to a guarded sibling in the same class.
                guarded_here = {
                    m.name for m in klass.body
                    if isinstance(m, ast.FunctionDef) and "_guard" in called(m)
                }
                for method in klass.body:
                    if not isinstance(method, ast.FunctionDef):
                        continue
                    names = called(method)
                    # Holding a session is not operating on one: a constructor
                    # that only stores it takes no decision because it performs
                    # nothing. The subject is the OPERATION, not the mention.
                    if not (names & SESSION_OPERATIONS):
                        continue
                    checked += 1
                    assert "_guard" in names or names & guarded_here, (
                        f"{path.name}::{klass.name}.{method.name} operates on "
                        "the session without a policy decision and without "
                        "delegating to a method that takes one"
                    )
        assert checked >= 10, "the sweep found too few session-operating methods"

    def test_every_service_class_consults_the_pep(self) -> None:
        """A service that holds a session must itself ask the PEP something.

        Package-level coverage is not enough: one module consulting a PEP does
        not make its neighbour governed.
        """
        for path in modules(DURABLE):
            source = read(path)
            if "_session" not in source:
                continue
            assert "require_auto" in called(ast.parse(source)), (
                f"{path.name} holds a session but never asks the PEP"
            )

    def test_the_write_path_requests_the_workspace_class(self) -> None:
        source = code_only(read(DURABLE / "job_store.py"))
        assert "_guard(WRITE)" in source
        assert "_guard(READ)" in source


class TestRetryAccountingIsPersistedNotCounted:
    """Package 2. The attempt history must live in rows, not in a number."""

    def test_no_attempt_counter_column_exists_on_the_job(self) -> None:
        """A counter is settable, resettable and can drift from what happened.

        NEGATIVE CONTROL for the shape the defect would take: any column on
        `durable_job` that looks like a running tally of attempts.
        """
        counters = {
            column.name for column in DurableJobRecord.__table__.columns
            if re.search(r"(attempt|retry|try)_?(count|counter|number|n)$",
                         column.name)
        }
        assert counters == set(), (
            f"{sorted(counters)} would be a counter; the count must be derived "
            "from job_execution_attempt rows"
        )

    def test_the_attempt_ordinal_is_part_of_the_primary_key(self) -> None:
        """The database is the concurrency backstop, not a service check."""
        primary = {c.name for c in JobExecutionAttempt.__table__.primary_key.columns}
        assert primary == {"job_id", "attempt"}

    def test_the_count_is_read_from_the_database(self) -> None:
        """`attempt_count` must query, not read an attribute."""
        tree = ast.parse(read(DURABLE / "execution.py"))
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "attempt_count"
        )
        names = called(method)
        assert "execute" in names and "count" in names, (
            "attempt_count does not query the attempt rows"
        )

    def test_the_bound_and_the_timeout_are_recorded_on_the_job(self) -> None:
        columns = {c.name for c in DurableJobRecord.__table__.columns}
        assert {"max_attempts", "attempt_timeout_seconds"} <= columns

    def test_the_deadline_is_an_absolute_instant(self) -> None:
        """A remaining-duration column would silently restart with the process."""
        deadline = JobExecutionAttempt.__table__.columns["deadline_at"]
        assert type(deadline.type).__name__ == "DateTime"
        assert deadline.nullable is False

    def test_the_disposition_targets_are_declared_transitions_of_failed(
        self,
    ) -> None:
        """Retry and dead-letter are edges the machine owns, not new states."""
        successors = {t for s, t in DEFINITION.transitions if s == "FAILED"}
        assert successors == {"RECOVERABLE", "DEAD_LETTER"}

    def test_the_execution_module_imports_its_targets_from_the_authority(
        self,
    ) -> None:
        """Positive counterpart to the no-state-literal control.

        Selecting which declared move to request is legitimate; the names must
        come from the machine module so a renamed state breaks at import rather
        than reaching `evaluate` as an unknown string.
        """
        tree = ast.parse(read(DURABLE / "execution.py"))
        imported_from_machine: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module.endswith("job_state_machine")
            ):
                imported_from_machine.update(a.name for a in node.names)
        assert {"RUNNING", "FAILED", "RECOVERABLE", "DEAD_LETTER"} <= (
            imported_from_machine
        )

    def test_the_execution_module_never_enters_resuming(self) -> None:
        """Package 3 boundary: recovery and resume are not pre-implemented."""
        source = code_only(read(DURABLE / "execution.py"))
        for forbidden in ("RESUMING", "PAUSED", "supports_pause"):
            assert forbidden not in source, (
                f"{forbidden} belongs to Package 3; Package 2 records what "
                "recovery will need and stops there"
            )


class TestContractAndSchemaAgree:
    def test_the_contract_document_exists_and_names_the_owner(self) -> None:
        text = read(CONTRACT_DOC)
        assert "C-19" in text
        assert "`execution.durable`" in text
        assert "**Phase:** 7" in text

    def test_every_mapped_column_is_documented(self) -> None:
        text = read(CONTRACT_DOC)
        for table in (DurableJobRecord, JobCheckpointRecord, JobExecutionAttempt):
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
        for table in (DurableJobRecord, JobCheckpointRecord, JobExecutionAttempt):
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
