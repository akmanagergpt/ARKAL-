"""C-11 `control.registry.provider` authority controls (Phase 9 Package 1).

Every subject is DERIVED from the deployed source and the canonical documents.
No concern name, consumer name, health state or phase number is transcribed, so
a canonical change moves these controls instead of leaving them stale - the
F-0032 lesson.

WHAT THESE EXIST TO CATCH. A registry that declares its own scope instead of
reading it; a second provider-health authority appearing beside the canonical
Phase 3 machine; persistence arriving in a contract the inventory marks `INT`;
a provider runtime or a Capability Graph activation pulled forward from Phase 9B
and later; and a raw secret becoming storable in a governed record.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

import pytest
import yaml

from arkali.control.registry.provider.provider_authority import ProviderAuthority
from arkali.control.registry.provider.provider_health_state_machine import DEFINITION
from arkali.control.registry.provider.provider_record import ProviderRecord

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE: Final[pathlib.Path] = REPO / "backend" / "arkali"
PROVIDER: Final[pathlib.Path] = PACKAGE / "control" / "registry" / "provider"
CONTRACT_DOC: Final[pathlib.Path] = REPO / "docs" / "contracts" / "provider_record.md"
MIGRATIONS: Final[pathlib.Path] = REPO / "backend" / "alembic" / "versions"
AUTHORITY_MAP: Final[pathlib.Path] = REPO / "docs/canonical/AUTHORITY_MAP.yaml"

#: The machine module legitimately declares the health vocabulary; every other
#: module in the context must read it rather than restate it.
MACHINE_MODULE: Final[str] = "provider_health_state_machine.py"

ENGINE_CONSTRUCTORS: Final[tuple[str, ...]] = (
    "create_engine", "create_async_engine", "sessionmaker", "async_sessionmaker",
    "declarative_base", "create_persistence_engine", "create_session_factory",
)
#: Provider EXECUTION, which is not what Phase 9 Package 1 builds.
RUNTIME_NAMES: Final[tuple[str, ...]] = (
    "invoke", "complete", "chat", "stream", "httpx", "requests", "urllib",
    "socket", "connect", "simulate", "fabricate",
)


def modules(root: pathlib.Path) -> list[pathlib.Path]:
    found = sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")
    assert found, f"no module under {root}; this control would be vacuous"
    return found


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


def imported(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def called(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def string_constants(path: pathlib.Path) -> set[str]:
    return {
        n.value for n in ast.walk(ast.parse(read(path)))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


@pytest.fixture(scope="module")
def authority() -> ProviderAuthority:
    return ProviderAuthority.load(REPO)


class TestTheScopeIsReadNotDeclared:
    """ARK-REQ-0052: a sole authority must derive its scope, not assert it."""

    def test_no_module_hard_codes_the_owned_concerns(
        self, authority: ProviderAuthority
    ) -> None:
        """A literal concern list outside the map would be a second declaration."""
        canonical = set(authority.owned_concerns())
        for path in modules(PROVIDER):
            leaked = sorted(string_constants(path) & canonical)
            assert not leaked, (
                f"{path.name} hard-codes owned concerns {leaked}; the scope is "
                "parsed from AUTHORITY_MAP.yaml, never copied"
            )

    def test_no_module_hard_codes_the_reference_only_consumers(
        self, authority: ProviderAuthority
    ) -> None:
        canonical = set(authority.reference_only_consumers())
        for path in modules(PROVIDER):
            leaked = sorted(string_constants(path) & canonical)
            assert not leaked, f"{path.name} hard-codes consumers {leaked}"

    def test_the_record_and_the_map_reconcile_in_both_directions(
        self, authority: ProviderAuthority
    ) -> None:
        assert set(ProviderRecord.model_fields) == set(authority.owned_concerns())

    def test_the_declared_scope_is_the_expected_shape(
        self, authority: ProviderAuthority
    ) -> None:
        """Anti-vacuity: a truncated parse must not silently weaken the controls."""
        assert len(authority.owned_concerns()) == 7
        assert len(authority.reference_only_consumers()) >= 5


class TestOneProviderHealthAuthority:
    """The Phase 3 machine is reused, never duplicated."""

    def test_only_the_machine_module_declares_health_states(self) -> None:
        states = set(DEFINITION.states)
        for path in modules(PROVIDER):
            if path.name == MACHINE_MODULE:
                continue
            leaked = sorted(string_constants(path) & states)
            assert not leaked, (
                f"{path.name} restates health states {leaked}; the canonical "
                f"{DEFINITION.machine} machine owns that vocabulary"
            )

    def test_no_second_state_machine_is_defined_in_this_context(self) -> None:
        for path in modules(PROVIDER):
            if path.name == MACHINE_MODULE:
                continue
            source = code_only(read(path))
            for name in ("StateMachineDefinition", "transitions=", "terminal="):
                assert name not in source, f"{path.name} declares {name!r}"

    def test_the_canonical_machine_authority_is_unchanged(self) -> None:
        raw = yaml.safe_load(AUTHORITY_MAP.read_text(encoding="utf-8"))
        authorities = raw["state_machine_authorities"]
        assert authorities[DEFINITION.machine] == DEFINITION.authority
        assert len(authorities) == 12, (
            f"the canonical state-machine count changed to {len(authorities)}"
        )


class TestNoPersistenceAuthority:
    """C-11 is `INT`, where C-12 is `DB+INT`. That difference is governed data."""

    def test_the_contract_inventory_still_declares_this_contract_int(self) -> None:
        rows = [
            line for line in
            (REPO / "docs/canonical/CONTRACT_INVENTORY.md").read_text(
                encoding="utf-8").splitlines()
            if re.match(r"^\|\s*C-11\s*\|", line)
        ]
        assert len(rows) == 1
        cells = [c.strip() for c in rows[0].split("|")]
        assert "INT" in cells and "DB+INT" not in cells, (
            "C-11's kind changed; the no-persistence reasoning must be re-derived"
        )

    def test_no_engine_or_session_is_constructed(self) -> None:
        for path in modules(PROVIDER):
            leaked = sorted(called(ast.parse(read(path))) & set(ENGINE_CONSTRUCTORS))
            assert not leaked, f"{path.name} constructs {leaked}"

    def test_no_persistence_module_is_imported(self) -> None:
        for path in modules(PROVIDER):
            for module in imported(ast.parse(read(path))):
                assert "persistence" not in module, f"{path.name} -> {module}"
                assert "sqlalchemy" not in module, f"{path.name} -> {module}"

    def test_package_one_adds_no_migration(self) -> None:
        migrations = sorted(MIGRATIONS.glob("*.py"))
        assert migrations, "no migration found; this control would be vacuous"
        for path in migrations:
            for node in ast.walk(ast.parse(read(path))):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)):
                    continue
                if not node.func.attr.endswith(("_table", "_column", "_index")):
                    continue
                for argument in node.args:
                    if (isinstance(argument, ast.Constant)
                            and isinstance(argument.value, str)):
                        assert "provider" not in argument.value.lower(), (
                            f"{path.name} builds provider schema; C-11 is INT"
                        )

    def test_the_record_is_a_value_not_a_mapped_row(self) -> None:
        bases = {b.__name__ for b in ProviderRecord.__mro__}
        assert "PersistenceBase" not in bases
        assert not hasattr(ProviderRecord, "__tablename__")


class TestNoRuntimeOrActivationIsPulledForward:
    """Phase 9 Package 1 declares. Phase 9B and later stay absent."""

    def test_no_provider_execution_is_implemented(self) -> None:
        for path in modules(PROVIDER):
            source = code_only(read(path)).lower()
            for name in RUNTIME_NAMES:
                assert name not in source, (
                    f"{path.name} names {name!r}; provider execution is not this "
                    "package"
                )

    def test_the_capability_graph_is_not_touched(self) -> None:
        """Activation is Phase 9B; the registry must not reach into it."""
        for path in modules(PROVIDER):
            for module in imported(ast.parse(read(path))):
                assert "capability" not in module, f"{path.name} -> {module}"
            source = code_only(read(path))
            for name in ("activate", "can_perform", "configured_state"):
                assert name not in source, f"{path.name} names {name!r}"

    def test_no_higher_layer_or_execution_context_is_imported(self) -> None:
        forbidden = ("arkali.execution", "arkali.engineering", "arkali.lifecycle",
                     "arkali.surfaces", "arkali.evidence", "arkali.acceptance")
        for path in modules(PROVIDER):
            for module in imported(ast.parse(read(path))):
                assert not module.startswith(forbidden), f"{path.name} -> {module}"

    def test_the_base_error_layer_is_used_rather_than_the_full_taxonomy(
        self,
    ) -> None:
        """`kernel.contracts.errors` is at its fan-in budget (F-0042)."""
        for path in modules(PROVIDER):
            for module in imported(ast.parse(read(path))):
                assert module != "arkali.kernel.contracts.errors", (
                    f"{path.name} imports the full taxonomy; use error_base"
                )


class TestTheContractDocumentReconciles:
    """C-11 declares a document; it must agree with the implementation."""

    def test_the_document_exists(self) -> None:
        assert CONTRACT_DOC.is_file(), f"C-11 declares {CONTRACT_DOC.name}"

    def test_the_document_lists_exactly_the_owned_concerns(
        self, authority: ProviderAuthority
    ) -> None:
        rows = re.findall(
            r"^\|\s*`([a-z_]+)`\s*\|", read(CONTRACT_DOC), re.M
        )
        assert set(rows) == set(authority.owned_concerns()), (
            f"the document lists {sorted(set(rows))}; the map declares "
            f"{sorted(authority.owned_concerns())}"
        )

    def test_the_document_declares_the_inventory_row_fields(self) -> None:
        header = read(CONTRACT_DOC)[:800]
        for token in ("control.registry.provider", "INT", "STRICT", "semver", "9"):
            assert token in header, f"the C-11 document omits {token!r}"
