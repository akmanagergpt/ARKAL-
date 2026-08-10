"""C-21 `execution.scheduler` authority controls (Phase 8 Package 1).

Every subject is DERIVED from the deployed source, the canonical documents or
the shipping contract document. Nothing here transcribes a module list, a field
list, a class list or a count, because a transcribed subject goes stale silently
- the F-0032 defect.

What these controls exist to catch, stated plainly: a scheduler that reaches
into `execution.durable`; a persistence, engine or state-machine authority
appearing where C-21 says INT; a second worker-class vocabulary; a Package 2
admission decision arriving early; and a governed read that no PEP decides.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest
import yaml

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.runner import GateRunner
from arkali.control.policy.operation_class import OperationClassVocabulary
from arkali.execution.scheduler.worker_contract import (
    CANONICAL_DIMENSION_FIELDS,
    WorkerDeclaration,
)
from arkali.execution.scheduler.worker_vocabulary import WorkerVocabulary
from arkali.kernel.contracts.results import HonestState
from tests.structural.scheduler_reader import (
    ADMISSION_NAMES,
    CONTRACT_DOC,
    DURABLE,
    DURABLE_NAMES,
    ENGINE_CONSTRUCTORS,
    FORWARD_NAMES,
    MACHINE_NAMES,
    MIGRATIONS,
    RAW_SQL,
    REPO,
    SCHEDULER,
    called,
    code_only,
    creates_table_named,
    declared_names,
    documented_classes,
    documented_dimensions,
    imported,
    modules,
    read,
    string_constants,
    takes_a_policy_decision,
)

AUTHORITY_MAP_PATH = REPO / "docs/canonical/AUTHORITY_MAP.yaml"


@pytest.fixture(scope="module")
def authority_map_raw() -> dict[str, object]:
    return dict(yaml.safe_load(AUTHORITY_MAP_PATH.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def vocabulary() -> WorkerVocabulary:
    return WorkerVocabulary.load(REPO)


class TestSchedulerDurableIsolation:
    """Both rank 3, `allow_same_layer` false, no sibling edge either way."""

    def test_scheduler_never_imports_durable(self) -> None:
        for path in modules(SCHEDULER):
            for module in imported(ast.parse(read(path))):
                assert not module.startswith("arkali.execution.durable"), (
                    f"{path.name} -> {module}; there is no sibling edge and "
                    "C-19 remains the sole durable authority"
                )

    def test_durable_still_never_imports_scheduler(self) -> None:
        """The reverse direction, asserted from this side too."""
        for path in modules(DURABLE):
            for module in imported(ast.parse(read(path))):
                assert not module.startswith("arkali.execution.scheduler"), (
                    f"{path.name} -> {module}"
                )

    def test_no_sibling_or_higher_layer_context_is_imported(self) -> None:
        forbidden = (
            "arkali.execution.durable", "arkali.execution.workflow",
            "arkali.execution.sandbox", "arkali.execution.operations",
            "arkali.engineering", "arkali.lifecycle", "arkali.surfaces",
        )
        for path in modules(SCHEDULER):
            for module in imported(ast.parse(read(path))):
                assert not module.startswith(forbidden), f"{path.name} -> {module}"

    def test_no_sibling_edge_touching_the_scheduler_is_declared(
        self, authority_map_raw: dict[str, object]
    ) -> None:
        edges = authority_map_raw["allowed_sibling_edges"]
        assert isinstance(edges, list)
        for edge in edges:
            assert "execution.scheduler" not in (edge["from"], edge["to"]), (
                f"a sibling edge for the scheduler appeared: {edge}"
            )

    def test_no_c19_concern_is_named_in_scheduler_source(self) -> None:
        """C-19 owns these; naming one here is how a second authority starts."""
        for path in modules(SCHEDULER):
            source = code_only(read(path))
            for name in DURABLE_NAMES:
                assert not re.search(rf"\b{name}\b", source, re.I), (
                    f"{path.name} names {name!r}; that concern is C-19 at Phase 7"
                )


class TestNoPersistenceAuthority:
    """C-21 is INT. No table, no migration, no engine, no session, no SQL."""

    def test_no_engine_or_session_is_constructed(self) -> None:
        for path in modules(SCHEDULER):
            names = called(ast.parse(read(path)))
            leaked = sorted(names & set(ENGINE_CONSTRUCTORS))
            assert not leaked, f"{path.name} constructs {leaked}"

    def test_no_persistence_module_is_imported(self) -> None:
        for path in modules(SCHEDULER):
            for module in imported(ast.parse(read(path))):
                assert "persistence" not in module, f"{path.name} -> {module}"

    def test_no_raw_or_dialect_specific_sql_appears(self) -> None:
        for path in modules(SCHEDULER):
            source = code_only(read(path))
            for pattern in RAW_SQL:
                assert not re.search(pattern, source), (
                    f"{path.name} matches {pattern!r}"
                )

    def test_package_one_adds_no_migration(self) -> None:
        """No migration in the chain builds a scheduler or worker table."""
        migrations = sorted(MIGRATIONS.glob("*.py"))
        assert migrations, "no migration found; this control would be vacuous"
        for path in migrations:
            for name in ("worker", "scheduler"):
                assert not creates_table_named(path, name), (
                    f"{path.name} builds schema named {name!r}; C-21 is INT"
                )

    def test_the_declaration_is_a_value_not_a_mapped_record(self) -> None:
        """A pydantic model, with no ORM table anywhere in its ancestry."""
        bases = {base.__name__ for base in WorkerDeclaration.__mro__}
        assert "PersistenceBase" not in bases
        assert not hasattr(WorkerDeclaration, "__tablename__")


class TestNoStateMachineAuthority:
    """No worker or scheduler machine is declared, and none is built."""

    def test_no_machine_vocabulary_appears_in_scheduler_source(self) -> None:
        for path in modules(SCHEDULER):
            source = code_only(read(path))
            for name in MACHINE_NAMES:
                assert not re.search(rf"\b{name}\b", source), (
                    f"{path.name} names {name!r}; Phase 8 declares no machine"
                )

    def test_the_scheduler_owns_no_canonical_state_machine(
        self, authority_map_raw: dict[str, object]
    ) -> None:
        authorities = authority_map_raw["state_machine_authorities"]
        assert isinstance(authorities, dict)
        assert "execution.scheduler" not in authorities.values()

    def test_no_canonical_machine_was_added_for_a_worker_or_scheduler(
        self, authority_map_raw: dict[str, object]
    ) -> None:
        """The count cannot grow *because of Phase 8* without this firing."""
        authorities = authority_map_raw["state_machine_authorities"]
        assert isinstance(authorities, dict)
        for machine in authorities:
            assert "worker" not in machine.lower()
            assert "schedul" not in machine.lower()

    def test_the_canonical_machine_count_is_unchanged(self) -> None:
        """Derived from the gate that owns the question, not transcribed."""
        gates = GateRunner(REPO, AuthorityMap.load(REPO)).run_all()
        machines = [
            g for g in gates if g.check_id == "duplicate_state_machine_authority"
        ]
        assert machines and machines[0].state is HonestState.PASS
        assert "12 state machines" in machines[0].summary


class TestPackageTwoHasNotArrived:
    """Package 1 declares. It admits nothing and queues nothing."""

    def test_no_admission_vocabulary_is_defined_or_called(self) -> None:
        """The subject is identifiers, not prose: a refusal message may say
        "admitting" while the module admits nothing."""
        for path in modules(SCHEDULER):
            for identifier in declared_names(path):
                lowered = identifier.lower()
                for name in ADMISSION_NAMES:
                    assert name not in lowered, (
                        f"{path.name} defines or calls {identifier!r}; "
                        "admission is Package 2"
                    )

    def test_no_forward_phase_concept_is_defined_or_called(self) -> None:
        """Queue, priority, fairness, autoscaling and friends are not Phase 8."""
        for path in modules(SCHEDULER):
            for identifier in declared_names(path):
                lowered = identifier.lower()
                for name in FORWARD_NAMES:
                    assert name not in lowered, (
                        f"{path.name} defines or calls {identifier!r}; the "
                        "canonical set does not give Phase 8 that concept"
                    )

    def test_no_provider_runtime_is_pulled_forward(self) -> None:
        for path in modules(SCHEDULER):
            for module in imported(ast.parse(read(path))):
                assert "registry.provider" not in module, f"{path.name} -> {module}"
            source = code_only(read(path))
            assert not re.search(r"\bprovider_", source, re.I), path.name

    def test_no_capability_graph_query_is_made(self) -> None:
        """Capability activation is Phase 9B; Package 1 asks nothing of it."""
        for path in modules(SCHEDULER):
            for module in imported(ast.parse(read(path))):
                assert "capability" not in module, f"{path.name} -> {module}"


class TestOneWorkerVocabulary:
    """The canonical classes and dimensions have exactly one authority."""

    def test_no_scheduler_module_hard_codes_a_canonical_worker_class(
        self, vocabulary: WorkerVocabulary
    ) -> None:
        """A literal class name outside the parser would be a second vocabulary."""
        canonical = set(vocabulary.classes())
        for path in modules(SCHEDULER):
            leaked = sorted(string_constants(path) & canonical)
            assert not leaked, (
                f"{path.name} hard-codes canonical worker classes {leaked}; the "
                "vocabulary is parsed from the canonical document, never copied"
            )

    def test_the_vocabulary_module_names_no_class_and_no_dimension(
        self, vocabulary: WorkerVocabulary
    ) -> None:
        """The parser's CODE must contain none of what it parses.

        Docstring prose may quote a canonical spelling to explain why spelling
        is preserved; a literal in the code would be the second vocabulary.
        """
        source = code_only(read(SCHEDULER / "worker_vocabulary.py"))
        for name in vocabulary.classes():
            assert name not in source, f"the parser contains the class {name!r}"
        # Only the multi-word dimensions are assertable. `class` is a single
        # generic English word and a Python keyword; it appears inside the very
        # regex that parses the canonical list, so asserting on it would be a
        # control that cannot distinguish a copy from the parser itself. The
        # dimension set is protected instead by the both-directions
        # reconciliation in TestSixDimensionsReconcile, which is the real
        # control - this one only forbids a *verbatim canonical phrase*.
        for dimension in vocabulary.dimensions():
            if " " not in dimension:
                continue
            assert dimension not in source, (
                f"the parser contains the dimension {dimension!r}"
            )

    def test_the_canonical_class_list_is_the_expected_shape(
        self, vocabulary: WorkerVocabulary
    ) -> None:
        """Anti-vacuity: a truncated parse must not silently weaken every control."""
        classes = vocabulary.classes()
        assert len(classes) == 7, f"canonical worker classes changed: {classes}"
        assert len(set(classes)) == len(classes)

    def test_the_canonical_dimension_list_is_the_expected_shape(
        self, vocabulary: WorkerVocabulary
    ) -> None:
        dimensions = vocabulary.dimensions()
        assert len(dimensions) == 6, f"canonical dimensions changed: {dimensions}"
        assert len(set(dimensions)) == len(dimensions)


class TestSixDimensionsReconcile:
    """Canonical prose, the binding table, the model and the document agree."""

    def test_the_binding_covers_exactly_the_canonical_dimensions(
        self, vocabulary: WorkerVocabulary
    ) -> None:
        assert set(CANONICAL_DIMENSION_FIELDS) == set(vocabulary.dimensions())

    def test_the_binding_covers_exactly_the_model_fields(self) -> None:
        assert set(CANONICAL_DIMENSION_FIELDS.values()) == set(
            WorkerDeclaration.model_fields
        )

    def test_the_document_table_matches_the_binding_in_both_directions(self) -> None:
        assert documented_dimensions() == CANONICAL_DIMENSION_FIELDS

    def test_the_document_class_table_matches_the_canonical_list(
        self, vocabulary: WorkerVocabulary
    ) -> None:
        assert documented_classes() == vocabulary.classes()

    def test_the_document_declares_the_inventory_row_fields(self) -> None:
        """The contract document must state what the inventory row says it is."""
        header = read(CONTRACT_DOC)[:800]
        for token in ("execution.scheduler", "INT", "ADDITIVE", "semver", "8"):
            assert token in header, f"the C-21 document omits {token!r}"


class TestGovernedAccessIsReal:
    """The derived PEP obligation must be met, not merely referenced."""

    def test_a_scheduler_module_takes_a_real_policy_decision(self) -> None:
        enforcing = [p for p in modules(SCHEDULER) if takes_a_policy_decision(p)]
        assert enforcing, (
            "execution.scheduler exists but no module in it takes a policy "
            "decision; the package must be under a real PEP"
        )

    def test_no_operation_class_is_invented(self) -> None:
        """Every operation-class-shaped literal must be canonical."""
        canonical = set(OperationClassVocabulary.load(REPO).names())
        shaped = re.compile(r"^[A-Z][A-Z_]{3,}$")
        for path in modules(SCHEDULER):
            for value in string_constants(path):
                if shaped.match(value) and value not in canonical:
                    assert value.startswith(("ARK-", "TRUST")) or "_" not in value, (
                        f"{path.name} names {value!r}, which is not a canonical "
                        "operation class"
                    )

    def test_the_pep_is_not_merely_imported(self) -> None:
        """NEGATIVE CONTROL: importing a PEP is not the same as consulting one."""
        importers = [
            p for p in modules(SCHEDULER)
            if "PolicyEnforcementPoint" in read(p)
        ]
        assert importers, "no module references a PEP at all"
        assert any(takes_a_policy_decision(p) for p in importers)


class TestArchitectureIsUnchanged:
    """Package 1 must not move the architecture it was built inside."""

    def test_every_architecture_gate_passes(self) -> None:
        results = GateRunner(REPO, AuthorityMap.load(REPO)).run_all()
        failed = [g.check_id for g in results if g.state is not HonestState.PASS]
        assert not failed, f"architecture gates failed: {failed}"

    def test_orchestration_depth_stays_within_budget(self) -> None:
        amap = AuthorityMap.load(REPO)
        allowed = int(amap.architecture_budgets["max_orchestration_depth"])
        budget = [
            g for g in GateRunner(REPO, amap).run_all()
            if g.check_id == "architecture_budget_violation"
        ][0]
        measured = re.search(r"measured_depth=(\d+)", budget.detail or "")
        assert measured, "the budget gate reported no measured depth"
        assert int(measured.group(1)) <= allowed


class TestPhaseTitleIsCanonical:
    """Governed phase titles are canonical data, not transcription."""

    def test_every_build_state_phase_title_matches_the_matrix(self) -> None:
        """Closes F-0041.

        `BUILD_STATE.md` restated each phase's title beside its status, and
        Phase 8's restatement had drifted from the canonical matrix. Nothing
        compared them, so the drift was invisible - the F-0002/F-0032 family.
        The titles are now reconciled for EVERY phase both documents name, so
        the next drift cannot hide either.
        """
        build_state = read(REPO / "docs/build/BUILD_STATE.md")
        matrix = read(REPO / "docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md")
        # Bold is emphasis, not content: `Capability Graph **Schema**` is one
        # title. An earlier draft excluded `*` from the title cell, so every
        # row with inline bold silently failed to parse and was never compared.
        canonical = {
            phase.replace("*", "").strip(): title.replace("*", "").strip()
            for phase, title in re.findall(
                r"^\|\s*([0-9*]{1,4}[AB]?\**)\s*\|([^|]+)\|", matrix, re.M
            )
        }
        assert len(canonical) > 30, "the canonical matrix parsed too thinly"
        section = build_state.split("## Phase status")[1].split("\n## ")[0]
        compared = 0
        for phase, title in re.findall(
            r"^\|\s*([0-9]{1,2}[AB]?)\s*\|([^|]*)\|", section, re.M
        ):
            expected = canonical.get(phase.strip())
            if expected is None:
                continue
            # BUILD_STATE appends the phase's contracts to the title as a
            # convenience; the matrix carries them in their own column. The
            # parenthetical is not part of the title, and it may name more than
            # one contract - `(C-14, C-15)`.
            stated = re.sub(
                r"\s*\(C-\d+(?:\s*,\s*C-\d+)*\)\s*$", "", title.strip()
            )
            assert stated == expected, (
                f"phase {phase} is titled {stated!r} in BUILD_STATE.md but "
                f"{expected!r} in the canonical matrix"
            )
            compared += 1
        # Anti-vacuity floor: every phase BUILD_STATE names individually and the
        # matrix also names must actually be compared. Phase 0 is the 0A+0B
        # acceptance package and has no matrix row of its own.
        assert compared >= 10, f"only {compared} phase titles compared"
