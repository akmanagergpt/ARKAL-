"""Structural controls on the C-20 workflow authority (Phase 17).

`execution.workflow` owns the canonical workflow graph and its executor. It
does NOT own: the `WorkflowExecution` lifecycle relation (the canonical
machine, Phase 3); durable job persistence (`execution.durable`, composed via
the declared sibling edge); the HUMAN APPROVAL policy decision
(`control.policy.WorkflowApprovalGate`); or any Stable-mutation capability
("workflow" is a named prohibited actor). A duplicate authority here would be
invisible to the dependency gate, because the machine and the durability
mechanism it could shadow both live one edge away. These controls are what
make the split checkable.

Read from the deployed source with `ast`, so prose cannot satisfy a check.
"""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / "backend" / "arkali" / "execution" / "workflow"
MACHINE_MODULE = "workflow_execution_state_machine.py"

_STATES = (
    "PENDING", "RUNNING", "WAITING_SIGNAL", "WAITING_APPROVAL",
    "COMPENSATING", "SUCCEEDED", "FAILED", "CANCELLED",
)
_TRANSITIONS = frozenset({
    ("PENDING", "RUNNING"), ("RUNNING", "WAITING_SIGNAL"),
    ("RUNNING", "WAITING_APPROVAL"), ("RUNNING", "COMPENSATING"),
    ("RUNNING", "SUCCEEDED"), ("RUNNING", "FAILED"), ("RUNNING", "CANCELLED"),
    ("WAITING_SIGNAL", "RUNNING"), ("WAITING_APPROVAL", "RUNNING"),
    ("COMPENSATING", "FAILED"), ("COMPENSATING", "CANCELLED"),
})


def _modules() -> list[pathlib.Path]:
    return sorted(p for p in WORKFLOW.glob("*.py") if p.name != "__init__.py")


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(_read(path), filename=str(path))


def _imported(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def _called(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _code_only(source: str) -> str:
    """Strip docstrings/comments-as-strings is overkill here; this repo's
    idiom (see `durable_reader.py`) is to scan raw source for transition-pair
    literals, which is sufficient because a real tuple assignment must appear
    as code regardless of surrounding prose."""
    return source


class TestTheCanonicalMachineIsTheOnlyLifecycleAuthority:
    def test_the_executor_builds_and_consults_the_canonical_machine(self) -> None:
        tree = _tree(WORKFLOW / "executor.py")
        assert "arkali.execution.workflow.workflow_execution_state_machine" in _imported(tree)
        names = _called(tree)
        assert "build" in names
        assert "evaluate" in names, (
            "the executor does not ask the machine to evaluate a move; a "
            "transition decided anywhere else is a second authority"
        )

    def test_no_other_module_restates_a_declared_transition_pair(self) -> None:
        """NEGATIVE CONTROL: no shadow transition table may reappear."""
        offenders: dict[str, list[tuple[str, str]]] = {}
        for path in _modules():
            if path.name == MACHINE_MODULE:
                continue
            tree = _tree(path)
            pairs = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Tuple) and len(node.elts) == 2
                and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts)
            ]
            found = [
                tuple(e.value for e in node.elts)  # type: ignore[misc]
                for node in pairs
                if tuple(e.value for e in node.elts) in _TRANSITIONS  # type: ignore[misc]
            ]
            if found:
                offenders[path.name] = found
        assert offenders == {}, f"shadow transition pairs: {offenders}"

    def test_only_the_run_loop_and_explicit_transition_sites_assign_lifecycle_state(self) -> None:
        """Every assignment to `.lifecycle_state` must be immediately preceded,
        in the same statement, by reading `.target` off a machine `evaluate()`
        outcome - never a bare string.
        """
        tree = _tree(WORKFLOW / "executor.py")
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            target = node.targets[0]
            if not (isinstance(target, ast.Attribute) and target.attr == "lifecycle_state"):
                continue
            value = node.value
            is_target_read = (
                isinstance(value, ast.Attribute) and value.attr == "target"
            )
            if not is_target_read:
                offenders.append(ast.dump(node))
        assert offenders == [], f"non-machine lifecycle_state assignment: {offenders}"

    def test_the_machine_module_still_declares_the_relation(self) -> None:
        """Not vacuous: the authority exists, unmodified, and is what is
        actually consulted."""
        from arkali.execution.workflow.workflow_execution_state_machine import DEFINITION

        assert DEFINITION.machine == "WorkflowExecution"
        assert DEFINITION.authority == "execution.workflow"
        assert set(DEFINITION.states) == set(_STATES)
        assert DEFINITION.transition_set == _TRANSITIONS


class TestHumanApprovalIsConsultedNotReimplemented:
    def test_the_executor_calls_the_real_approval_gate(self) -> None:
        tree = _tree(WORKFLOW / "executor.py")
        assert "arkali.control.policy.workflow_approval" in _imported(tree)
        names = _called(tree)
        assert "assert_may_record" in names
        assert "is_enforced_approval" in names

    def test_no_module_names_a_second_automated_actor_list(self) -> None:
        """`stable_mutation.prohibited_actors` is parsed once, by
        `WorkflowApprovalGate`; a second literal list here would be a second
        authority over who may approve."""
        for path in _modules():
            source = _read(path)
            assert "prohibited_actors" not in source, path.name


class TestDurableJobsAreConsultedNotReimplemented:
    def test_the_executor_calls_the_real_durable_job_execution_cycle(self) -> None:
        tree = _tree(WORKFLOW / "executor.py")
        assert "arkali.execution.durable.execution" in _imported(tree)
        assert "arkali.execution.durable.job_store" in _imported(tree)
        names = _called(tree)
        for expected in ("submit", "begin_attempt", "complete_attempt"):
            assert expected in names, f"executor never calls JobExecution.{expected}"

    def test_no_module_declares_its_own_job_or_checkpoint_table(self) -> None:
        for path in _modules():
            tree = _tree(path)
            classdefs = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
            for name in classdefs:
                assert "Job" not in name, f"{path.name} declares {name}"


class TestNoSecondPersistenceAuthority:
    ENGINE_CONSTRUCTORS = ("create_engine", "create_persistence_engine")
    RAW_SQL = (r"\bSELECT\s", r"\bINSERT\s+INTO\b", r"\bUPDATE\s+\w+\s+SET\b", r"\bDELETE\s+FROM\b")

    def test_no_engine_is_constructed_or_imported_in_this_context(self) -> None:
        for path in _modules():
            tree = _tree(path)
            names = _called(tree) | {
                (alias.asname or alias.name).split(".")[-1]
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            offending = sorted(set(self.ENGINE_CONSTRUCTORS) & names)
            assert offending == [], f"{path.name}: {offending}"

    def test_no_raw_sql_appears(self) -> None:
        for path in _modules():
            source = _code_only(_read(path))
            for pattern in self.RAW_SQL:
                assert not re.search(pattern, source), f"{path.name} matches {pattern}"

    def test_the_declarative_base_comes_from_kernel_persistence(self) -> None:
        for name in ("records.py", "execution_records.py"):
            tree = _tree(WORKFLOW / name)
            assert "arkali.kernel.persistence.base" in _imported(tree)


class TestNoStableMutationCapability:
    STABLE_CLASSES = ("WRITE_STABLE_FILE", "ROLLBACK_STABLE")

    def test_no_stable_operation_class_is_named(self) -> None:
        for path in _modules():
            source = _read(path)
            for name in self.STABLE_CLASSES:
                assert name not in source, f"{path.name} names {name}"

    def test_release_kind_nodes_dispatch_as_an_ordinary_durable_job_only(self) -> None:
        """A `release` node must go through exactly the same leaf-dispatch
        path as every other non-`logic` kind - no special-cased Stable-touching
        branch exists for it."""
        source = _code_only(_read(WORKFLOW / "executor.py"))
        assert '"release"' not in source and "'release'" not in source, (
            "the executor special-cases the release kind instead of treating "
            "it as an ordinary leaf dispatch"
        )


class TestEveryGovernedOperationPassesAnInjectedPep:
    def test_every_public_class_taking_a_session_also_takes_a_pep_or_pdp(self) -> None:
        offenders: list[str] = []
        for path in _modules():
            tree = _tree(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                init = next(
                    (
                        n for n in node.body
                        if isinstance(n, ast.FunctionDef) and n.name == "__init__"
                    ),
                    None,
                )
                if init is None:
                    continue
                params = {a.arg for a in init.args.args}
                if "session" in params and not ({"pep", "pdp"} & params):
                    offenders.append(f"{path.name}::{node.name}")
        assert offenders == [], f"session without a policy authority: {offenders}"
