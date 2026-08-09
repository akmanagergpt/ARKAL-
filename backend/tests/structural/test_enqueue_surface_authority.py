"""Structural controls on the `ARK-REQ-0027` enqueue surface (Package 4).

`MS §Constitution 8` — no long AI work in HTTP requests — is registered with
`arch` evidence. That means the guarantee has to be a property of the
architecture rather than an observation about how fast a route happened to run,
and these controls are that half of it: the handler is not *able* to execute a
job, because everything that could is absent from it.

Everything is read from the DEPLOYED SOURCE with `ast`, so prose cannot satisfy
a check, and the forbidden call sets are DERIVED from the durable services
themselves rather than transcribed — a method added to `JobExecution` or
`JobRecovery` later is covered without editing this file.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re
from typing import Final

from arkali.execution.durable.execution import JobExecution
from arkali.execution.durable.job_store import JobStore
from arkali.execution.durable.recovery import JobRecovery
from arkali.surfaces.command import contracts
from arkali.surfaces.command.contracts import ROUTE_AUDIENCES, JobReferenceResponse
from arkali.surfaces.command.error_mapping import (
    DOMAIN_ERROR_BASE,
    mapped_error_types,
    status_for,
)
from arkali.surfaces.command.job_error_mapping import durable_error_types

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE: Final[pathlib.Path] = REPO / "backend" / "arkali"
SURFACE: Final[pathlib.Path] = PACKAGE / "surfaces" / "command"
JOBS: Final[pathlib.Path] = SURFACE / "jobs.py"

#: Anything that would mean the surface had built its own persistence authority.
ENGINE_CONSTRUCTORS: Final[tuple[str, ...]] = (
    "create_engine", "create_async_engine", "sessionmaker",
    "async_sessionmaker", "declarative_base", "create_persistence_engine",
    "create_session_factory",
)
#: Anything that would mean raw or ORM query authority had appeared in a route.
QUERY_AUTHORITY: Final[tuple[str, ...]] = (
    "execute", "query", "select", "insert", "update", "delete", "text",
    "add", "flush", "commit",
)
#: Phase 8 and later. Present here would be a pull-forward.
FORWARD_NAMES: Final[tuple[str, ...]] = (
    "scheduler", "worker", "dispatch", "allocate", "admission", "admit",
    "capacity", "priority", "queue_position", "provider", "model_runtime",
    "completion", "inference",
)
#: Shapes that would mean the request waited for the work instead of enqueuing.
WAITING_SHAPES: Final[tuple[str, ...]] = (
    r"\bsleep\b", r"\bwait\b", r"\bpoll\b", r"\bjoin\b", r"\bawait_result\b",
    r"\bwhile\s+True\b", r"\bas_completed\b", r"\bgather\b", r"\bfuture\b",
    r"\bThread\b", r"\bProcess\b", r"\bexecutor\b",
)


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
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


def route_functions() -> dict[str, ast.FunctionDef]:
    """Every function in `jobs.py` decorated with a router method.

    Derived from the decorators, so a route added later is measured by every
    control below without anyone remembering to list it.
    """
    found = {
        node.name: node
        for node in ast.walk(ast.parse(read(JOBS)))
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr in {"get", "post", "put", "patch", "delete"}
            for d in node.decorator_list
        )
    }
    assert found, "no route found in jobs.py; every control here would be vacuous"
    return found


def execution_driving_methods() -> frozenset[str]:
    """Everything that runs, advances or disposes of a job — derived.

    The public surface of the two execution services, plus the state recorder,
    minus the read-only questions. Calling any of them from an HTTP handler is
    executing the work, waiting on it, or moving it — which is the thing
    `ARK-REQ-0027` forbids.
    """
    readers = {
        "attempts", "attempt_count", "current_attempt", "retry_permitted",
        "timed_out", "heartbeat_stale", "jobs", "execution", "job_types",
        "get", "require", "find_submitted", "checkpoints",
        "next_checkpoint_sequence", "declared", "supports_pause", "machine_name",
    }
    driving = {
        name
        for service in (JobExecution, JobRecovery)
        for name, _ in inspect.getmembers(service, callable)
        if not name.startswith("__")
    }
    driving.add("transition")
    return frozenset(driving - readers)


class TestTheRouteCannotExecuteTheWork:
    def test_no_route_calls_anything_that_drives_execution(self) -> None:
        """The `arch` half of `ARK-REQ-0027`, derived not transcribed.

        NEGATIVE CONTROL for the shape the defect would take: a handler that
        opens an attempt, advances a state, runs a sweep or closes an attempt
        before responding.
        """
        forbidden = execution_driving_methods()
        assert len(forbidden) >= 8, (
            f"only {len(forbidden)} driving methods derived; the control would "
            "be weaker than the list it replaced"
        )
        for name, node in route_functions().items():
            offending = sorted(called(node) & forbidden)
            assert offending == [], (
                f"jobs.py::{name} calls {offending}; an HTTP request may enqueue "
                "durable work and must not perform it"
            )

    def test_the_enqueue_route_calls_submit_and_nothing_else_that_writes(
        self,
    ) -> None:
        """Positive counterpart, so the control above is not passing vacuously."""
        enqueue = route_functions()["enqueue_job"]
        names = called(enqueue)
        assert "submit" in names, "the enqueue route does not persist anything"
        assert "guard" in names, "the enqueue route takes no policy decision"

    def test_nothing_in_the_surface_waits_polls_or_spawns(self) -> None:
        """NEGATIVE CONTROL for waiting on completion by any spelling."""
        source = code_only(read(JOBS))
        for shape in WAITING_SHAPES:
            assert not re.search(shape, source), (
                f"jobs.py matches {shape}; the request must return after the "
                "durable write, not wait for the work"
            )

    def test_no_provider_or_scheduler_vocabulary_appears(self) -> None:
        """Provider runtime and C-21 are later phases and absent from here.

        STRENGTHENED BY A MISSED MUTATION. This was a `\\bname\\b` search over
        the source, which cannot match a compound identifier: `_` is a word
        character, so `\\bprovider\\b` does not match `provider_completion` -
        and a compound is the *likely* real spelling (`provider_client`,
        `call_provider`, `model_runtime_invoke`). An injected
        `provider_completion(...)` passed the old form. The subject is now every
        identifier the module declares, imports or calls, taken from the AST,
        and a forbidden token anywhere inside one of them fails.
        """
        tree = ast.parse(read(JOBS))
        identifiers: set[str] = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        identifiers |= {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        identifiers |= {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    # BOTH names, not `asname or name`. A second missed
                    # mutation: `from x import provider_client as pc` binds
                    # `pc`, so taking only the bound name lets an alias hide
                    # exactly the identifier this control exists to find.
                    identifiers.add(alias.name)
                    identifiers |= set(alias.name.split("."))
                    if alias.asname:
                        identifiers.add(alias.asname)
                if isinstance(node, ast.ImportFrom) and node.module:
                    identifiers.add(node.module)
                    identifiers |= set(node.module.split("."))
        assert identifiers, "no identifier found; this control would be vacuous"
        for identifier in identifiers:
            for name in FORWARD_NAMES:
                assert name not in identifier.lower(), (
                    f"jobs.py declares or calls {identifier!r}, which contains "
                    f"{name!r}; provider runtime and scheduling are later phases"
                )

    def test_no_sibling_execution_context_is_imported(self) -> None:
        forbidden = (
            "arkali.execution.scheduler", "arkali.execution.workflow",
            "arkali.execution.sandbox",
        )
        for module in imported(ast.parse(read(JOBS))):
            assert not module.startswith(forbidden), f"jobs.py -> {module}"


class TestTheRouteDelegatesAndOwnsNoPersistence:
    def test_the_route_module_constructs_no_engine_or_session_factory(
        self,
    ) -> None:
        tree = ast.parse(read(JOBS))
        names = called(tree) | {
            (alias.asname or alias.name).split(".")[-1]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        offending = sorted(set(ENGINE_CONSTRUCTORS) & names)
        assert offending == [], (
            f"jobs.py reaches for {offending}; the engine is built by "
            "kernel.persistence and the session arrives as a dependency"
        )

    def test_no_route_issues_a_query_of_its_own(self) -> None:
        """Delegation, not data access — the Phase 5 rule, restated for jobs."""
        for name, node in route_functions().items():
            offending = sorted(called(node) & set(QUERY_AUTHORITY))
            assert offending == [], (
                f"jobs.py::{name} issues {offending}; every read and write goes "
                "through JobStore"
            )

    def test_no_raw_sql_appears(self) -> None:
        source = code_only(read(JOBS))
        for pattern in (r"\btext\s*\(", r"\bPRAGMA\b", r"\bsqlite3\b", r"SELECT "):
            assert not re.search(pattern, source), f"jobs.py matches {pattern}"

    def test_the_route_holds_no_mapped_record_type_beyond_projection(
        self,
    ) -> None:
        """`DurableJobRecord` may be READ to project it, never constructed."""
        tree = ast.parse(read(JOBS))
        constructed = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "DurableJobRecord" not in constructed, (
            "the surface builds a durable record itself instead of delegating"
        )

    def test_idempotency_is_not_reimplemented_here(self) -> None:
        """NEGATIVE CONTROL: no surface-local cache, set or seen-map.

        An in-memory idempotency store would forget on restart, which is the
        one condition durability exists for. The guarantee is C-19's persisted
        unique constraint and the route must simply call it.
        """
        source = code_only(read(JOBS))
        for shape in (
            r"\bcache\b", r"\bseen\b", r"\b_submitted\b", r"\blru_cache\b",
            r"\bdefaultdict\b", r"\bset\(\)", r"\{\}\s*#",
        ):
            assert not re.search(shape, source), f"jobs.py matches {shape}"
        assert "find_submitted" not in called(ast.parse(source)), (
            "the route performs its own idempotency lookup; submit already is "
            "idempotent by the persisted constraint"
        )

    def test_no_lifecycle_state_is_assigned_by_the_surface(self) -> None:
        """NEGATIVE CONTROL: the canonical machine is the only authority."""
        for node in ast.walk(ast.parse(read(JOBS))):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for target in targets:
                assert not (
                    isinstance(target, ast.Attribute)
                    and target.attr == "lifecycle_state"
                ), "the surface writes a lifecycle state directly"

    def test_no_state_literal_or_transition_table_is_restated(self) -> None:
        """A second copy of the Job vocabulary here would be a shadow authority."""
        from arkali.execution.durable.job_state_machine import DEFINITION

        literals = {
            node.value for node in ast.walk(ast.parse(read(JOBS)))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert literals & set(DEFINITION.states) == set(), (
            "jobs.py restates a canonical Job state"
        )
        source = code_only(read(JOBS))
        assert not any(
            f"{a}->{b}" in source for a, b in DEFINITION.transitions
        )


class TestEveryRouteIsGovernedAndClassified:
    def test_every_route_takes_a_policy_decision(self) -> None:
        """NEGATIVE CONTROL: no route may skip the guard."""
        for name, node in route_functions().items():
            assert "guard" in called(node), (
                f"jobs.py::{name} performs an operation without a policy decision"
            )

    def test_only_the_two_workspace_classes_are_requested(self) -> None:
        """No new operation class is invented, and no Stable class is named."""
        source = read(JOBS)
        for stable in ("WRITE_STABLE_FILE", "ROLLBACK_STABLE"):
            assert stable not in source, f"jobs.py names {stable}"

    def test_the_operation_classes_are_imported_from_the_owning_context(
        self,
    ) -> None:
        """Imported, not restated: a third spelling would be a second vocabulary."""
        names: set[str] = set()
        for node in ast.walk(ast.parse(read(JOBS))):
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module.endswith("job_store")
            ):
                names.update(alias.name for alias in node.names)
        assert {"READ", "WRITE"} <= names

    def test_the_router_declares_its_audience(self) -> None:
        source = code_only(read(JOBS))
        assert "BACKEND_ONLY" in source, (
            "the jobs router declares no audience; the contract-drift control "
            "fails closed on an unclassified route"
        )
        assert "BACKEND_ONLY" in {
            name for name in dir(contracts) if not name.startswith("_")
        }
        assert len(ROUTE_AUDIENCES) == 2


class TestTheResponseContractExposesNothingInternal:
    def test_the_reference_carries_only_the_declared_fields(self) -> None:
        assert set(JobReferenceResponse.model_fields) == {
            "job_id", "job_type", "idempotency_key", "lifecycle_state",
            "created_at",
        }

    def test_no_executional_or_scheduling_field_is_representable(self) -> None:
        """NEGATIVE CONTROL over the declared shape, not over one response."""
        for field in JobReferenceResponse.model_fields:
            for token in (
                "owner", "attempt", "heartbeat", "deadline", "retry", "worker",
                "queue", "priority", "capacity", "path", "url", "engine",
            ):
                assert token not in field, f"{field} exposes {token}"

    def test_the_response_model_forbids_extra_fields(self) -> None:
        """So a future field cannot arrive on the wire without being declared."""
        assert JobReferenceResponse.model_config["extra"] == "forbid"


class TestTheDurableErrorContractIsReachable:
    def test_every_durable_error_type_maps_to_a_status(self) -> None:
        for error_type in durable_error_types():
            assert status_for(error_type("probe")) is not None, (
                f"{error_type.__name__} has no mapped status"
            )

    def test_the_durable_table_adds_to_the_project_table_without_shadowing(
        self,
    ) -> None:
        """The two halves must be disjoint, or composition could hide an entry."""
        durable = set(durable_error_types())
        everything = set(mapped_error_types())
        assert durable <= everything
        assert len(everything) == len(mapped_error_types()), "duplicate entries"

    def test_every_mapped_error_derives_from_the_registered_base(self) -> None:
        """CLOSES F-0039's other half.

        The application registers one handler for `DOMAIN_ERROR_BASE`. If a
        mapped type did not derive from it, that type's mapping would be
        unreachable exactly the way `PolicyDenied`'s was — so the base is
        checked against the table rather than assumed.
        """
        for error_type in mapped_error_types():
            assert issubclass(error_type, DOMAIN_ERROR_BASE), (
                f"{error_type.__name__} is mapped but the handler registered "
                f"for {DOMAIN_ERROR_BASE.__name__} would never receive it"
            )
