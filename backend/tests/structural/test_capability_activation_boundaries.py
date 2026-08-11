"""Boundaries of the activated Capability Graph (Phase 9B, Package 1).

Every subject is DERIVED from the deployed source, `AUTHORITY_MAP.yaml` or the
canonical capability schema. No context, authority, field or concern is written
out here, so a canonical change moves these controls instead of expiring them —
the F-0032 lesson.

What this module asserts is what activation must NOT become: a second graph, a
second capability authority, a second store of provider state, a cache, or a
quiet promotion of the pre-activation answer into a success.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

import pytest
import yaml

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.authority_gates import ShadowRegistryGate
from arkali.control.architecture.gates.base import GateContext
from arkali.control.capability.capability_graph import (
    CapabilityGraph,
    CapabilityQueryResult,
)
from arkali.control.capability.capability_node import CapabilityNode
from arkali.control.capability.reference_authority import (
    AUTHORITY_MAP_RELPATH,
    CapabilityReferenceAuthority,
)
from arkali.kernel.contracts.capability_errors import PrematureActivation
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE: Final[pathlib.Path] = REPO / "backend" / "arkali"

#: The context that owns `capability_availability_answer`. Read from the map
#: rather than written, so a renamed owner renames this subject.
OWNED_CONCERN: Final[str] = "capability_availability_answer"

#: The marker of the canonical node schema block. A module that parses it is
#: deriving the reference binding, and only the owner may.
SCHEMA_BLOCK_MARKER: Final[str] = "capability_node:"

#: Names that would mean a second state machine had appeared in this context.
MACHINE_NAMES: Final[tuple[str, ...]] = (
    "StateMachine", "state_machine", "TransitionOutcome", "forbidden_pair",
    "terminal_state", "transition_table",
)


def modules(root: pathlib.Path) -> list[pathlib.Path]:
    found = sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")
    assert found, f"no module under {root}; this control would be vacuous"
    return found


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def tree_of(path: pathlib.Path) -> ast.Module:
    return ast.parse(read(path), filename=str(path))


def imported(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def authority_map_raw() -> dict[str, object]:
    raw = yaml.safe_load(read(REPO / AUTHORITY_MAP_RELPATH))
    assert isinstance(raw, dict), "authority map did not parse to a mapping"
    return raw


def owner_context() -> str:
    """The single context the canonical map gives the capability answer to."""
    raw = authority_map_raw()
    owners = [
        str(entry["owner"])
        for entry in raw["concerns"]  # type: ignore[index]
        if entry.get("concern") == OWNED_CONCERN  # type: ignore[union-attr]
    ]
    assert len(owners) == 1, f"{OWNED_CONCERN} must have exactly one owner"
    return owners[0]


def context_root(context: str) -> pathlib.Path:
    raw = authority_map_raw()
    declared = raw["contexts"][context]  # type: ignore[index]
    return REPO / str(declared["module_root"])  # type: ignore[index]


def layer_ranks() -> dict[str, int]:
    raw = authority_map_raw()
    return {str(layer["name"]): int(layer["rank"]) for layer in raw["layers"]}  # type: ignore[index,union-attr]


def rank_of(context: str) -> int:
    raw = authority_map_raw()
    layer = str(raw["contexts"][context]["layer"])  # type: ignore[index]
    return layer_ranks()[layer]


class TestResolutionMustBeInjectedBecauseTheImportIsForbidden:
    """The design is forced by the layer rule, not chosen for taste."""

    def test_every_referenced_authority_is_the_owner_s_own_layer(self) -> None:
        authority = CapabilityReferenceAuthority.load(REPO)
        owner = owner_context()
        assert authority.authorities(), "no external authority; control vacuous"
        for name in authority.authorities():
            assert rank_of(name) == rank_of(owner), (
                f"{name} is not the same layer rank as {owner}; the reason this "
                "context may not import it would no longer hold"
            )

    def test_same_layer_edges_remain_forbidden_and_unexempted(self) -> None:
        raw = authority_map_raw()
        rules = raw["dependency_rules"]  # type: ignore[index]
        assert rules["allow_same_layer"] is False  # type: ignore[index]
        owner = owner_context()
        siblings = [
            edge for edge in raw["allowed_sibling_edges"]  # type: ignore[index]
            if edge.get("from") == owner  # type: ignore[union-attr]
        ]
        assert not siblings, f"{owner} has gained a sibling edge; re-derive Package 1"

    def test_the_owner_imports_no_referenced_authority(self) -> None:
        authority = CapabilityReferenceAuthority.load(REPO)
        forbidden = {f"arkali.{name}" for name in authority.authorities()}
        seen = 0
        for path in modules(context_root(owner_context())):
            found = imported(tree_of(path))
            seen += len(found)
            for module in found:
                for banned in forbidden:
                    assert not module.startswith(banned), (
                        f"{path.name} imports {module!r}; a same-layer authority "
                        "is reached by injected interface, never by import"
                    )
        assert seen, "no import observed at all; this control would be vacuous"

    def test_the_owner_does_not_lean_on_the_policy_exemption(self) -> None:
        """`policy_callable_from_any_layer` exists for PEP call sites.

        Phase 6 Package 2 and Phase 9 Package 1 both declined to be the first
        live edge to lean on it. Activation declines too.
        """
        raw = authority_map_raw()
        assert raw["dependency_rules"]["policy_callable_from_any_layer"] is True  # type: ignore[index]
        for path in modules(context_root(owner_context())):
            for module in imported(tree_of(path)):
                assert not module.startswith("arkali.control.policy"), (
                    f"{path.name} reaches control.policy directly"
                )

    def test_the_resolver_question_cannot_carry_a_value(self) -> None:
        """One method, returning bool. A value returned is a value stored."""
        owner = context_root(owner_context())
        protocols = [
            node
            for path in modules(owner)
            for node in ast.walk(tree_of(path))
            if isinstance(node, ast.ClassDef)
            and any("Protocol" in ast.unparse(base) for base in node.bases)
        ]
        assert protocols, "no resolver protocol found; control vacuous"
        for protocol in protocols:
            methods = [
                child for child in protocol.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            assert len(methods) == 1, (
                f"{protocol.name} asks more than one question of an authority"
            )
            returns = methods[0].returns
            assert returns is not None and ast.unparse(returns) == "bool", (
                f"{protocol.name}.{methods[0].name} returns "
                f"{ast.unparse(returns) if returns else 'nothing'}; a resolver "
                "reports whether a reference resolves, never what it holds"
            )


class TestThereIsExactlyOneCapabilityAuthority:
    def test_no_second_node_model_or_graph_exists(self) -> None:
        owner = context_root(owner_context())
        declared = {CapabilityNode.__name__: [], CapabilityGraph.__name__: []}
        for path in modules(PACKAGE):
            for node in ast.walk(tree_of(path)):
                if isinstance(node, ast.ClassDef) and node.name in declared:
                    declared[node.name].append(path)
        for name, paths in declared.items():
            assert len(paths) == 1, f"{name} is declared {len(paths)} times: {paths}"
            assert owner in paths[0].parents, f"{name} lives outside {owner}"

    def test_only_the_owner_parses_the_canonical_schema_block(self) -> None:
        owner = context_root(owner_context())
        parsing = [
            path.relative_to(PACKAGE).as_posix()
            for path in modules(PACKAGE)
            if owner not in path.parents and SCHEMA_BLOCK_MARKER in read(path)
        ]
        assert not parsing, (
            f"these modules derive the capability reference binding: {parsing}; "
            "a second binding table is a second authority"
        )
        assert any(
            SCHEMA_BLOCK_MARKER in read(path) for path in modules(owner)
        ), "the owner derives no binding; this control would be vacuous"

    def test_only_the_owner_composes_a_capability_verdict(self) -> None:
        """Package 2 makes a verdict constructible. Only its owner may build one.

        `execution.scheduler` returns the authority's own result unchanged; a
        module that CONSTRUCTED a `CapabilityQueryResult` would be answering the
        capability question itself, which is a second authority for the concern
        `AUTHORITY_MAP.yaml` gives to exactly one owner.
        """
        owner = context_root(owner_context())
        verdict = CapabilityQueryResult.__name__
        building = []
        for path in modules(PACKAGE):
            if owner in path.parents:
                continue
            for node in ast.walk(tree_of(path)):
                if isinstance(node, ast.Call) and _named(node.func) == verdict:
                    building.append(path.relative_to(PACKAGE).as_posix())
        assert not building, (
            f"these shipping modules construct a {verdict}: {sorted(set(building))}"
        )
        assert any(
            _named(node.func) == verdict
            for path in modules(owner)
            for node in ast.walk(tree_of(path))
            if isinstance(node, ast.Call)
        ), "the owner constructs no verdict; this control would be vacuous"

    def test_the_owner_declares_no_isolation_or_policy_vocabulary(self) -> None:
        """The activated query must not usurp another authority's verdict.

        Isolation satisfiability is `control.isolation` plus admission condition
        (b); a policy decision is the PDP's. Resolving a reference asks whether
        an identifier exists, never what it decides.
        """
        raw = authority_map_raw()
        isolation = raw["isolation"]  # type: ignore[index]
        canonical = set(isolation["properties"]) | set(isolation["tier_requirements"])  # type: ignore[index,call-overload]
        canonical |= {"AUTO", "ASK_USER", "DENY"}
        assert canonical, "no vocabulary derived; this control would be vacuous"
        for path in modules(context_root(owner_context())):
            declared = {
                node.id if isinstance(node, ast.Name) else node.attr
                for node in ast.walk(tree_of(path))
                if isinstance(node, (ast.Name, ast.Attribute))
            }
            leaked = sorted(declared & canonical)
            assert not leaked, f"{path.name} names {leaked}"

    def test_the_owner_declares_no_state_machine(self) -> None:
        """The canonical machine count stays 12; activation adds none."""
        for path in modules(context_root(owner_context())):
            source = read(path)
            for name in MACHINE_NAMES:
                assert name not in source, f"{path.name} names {name!r}"


class TestNoProviderStateAndNoCache:
    def test_the_live_shadow_registry_gate_passes_over_this_context(self) -> None:
        """The real gate, over the real repository, after Package 1's modules."""
        gate = ShadowRegistryGate()
        result = gate.evaluate(GateContext(REPO, AuthorityMap.load(REPO)))
        assert result.state is HonestState.PASS, result.detail
        owned = len(modules(context_root(owner_context())))
        scanned = int(result.summary.split(" consumer modules")[0].split()[-1])
        assert scanned >= owned, (
            f"the gate scanned {scanned} modules but this context alone holds "
            f"{owned}; Package 1's modules were not covered"
        )

    def test_no_module_retains_a_resolution_outcome(self) -> None:
        """Structural no-cache: an answer may be returned, never kept."""
        for path in modules(context_root(owner_context())):
            for node in ast.walk(tree_of(path)):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = getattr(node, "value", None)
                if value is None or not _calls_resolution(value):
                    continue
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    assert not _outlives_the_call(target), (
                        f"{path.name}:{node.lineno} keeps a resolution outcome; "
                        "every query must re-ask the authority"
                    )

    def test_the_owner_declares_no_provider_lookup_of_its_own(self) -> None:
        """A dict keyed by provider identities would be a second registry."""
        raw = authority_map_raw()
        owned = {
            str(field).lower()
            for field in raw["provider_authority"]["fields_owned"]  # type: ignore[index]
        }
        assert owned, "no owned concern declared; control vacuous"
        for path in modules(context_root(owner_context())):
            for node in ast.walk(tree_of(path)):
                if not isinstance(node, ast.Dict):
                    continue
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        assert key.value.lower() not in owned, (
                            f"{path.name}:{key.lineno} keys a mapping by the "
                            f"provider-owned concern {key.value!r}"
                        )


def _named(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _calls_resolution(value: ast.expr) -> bool:
    for node in ast.walk(value):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("resolve", "resolves", "resolve_references"):
                return True
    return False


def _outlives_the_call(target: ast.expr) -> bool:
    """An attribute on self is storage. A local is ordinary use."""
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    )


#: The two designed pre-activation tripwires Phase 9B Package 2 retired, and the
#: permanent control that replaced each. These are named rather than derived
#: because they are two specific historical artifacts; nothing derives "the test
#: that used to assert PrematureActivation". The control below is what stops a
#: replacement from being quietly emptied after the tripwire was removed.
TRIPWIRE_REPLACEMENTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "backend/tests/capability/test_capability_preactivation.py",
        "test_reaching_the_activation_phase_alone_invents_no_verdict",
    ),
    (
        "backend/tests/execution/test_admission_decision.py",
        "test_the_scheduler_cannot_force_a_configured_verdict",
    ),
)


class TestRetiredTripwiresStillHaveTheirObligation:
    """A tripwire may be replaced. Its obligation may not be dropped.

    `TRIPWIRE_REPLACEMENTS` is data in the SAME file as this control, so an edit
    that shrinks the tuple would silently narrow what gets checked rather than
    failing anything - the tuple is asserted against its own known length first,
    closing that hole before any entry is examined.
    """

    def test_the_replacement_set_itself_was_not_narrowed(self) -> None:
        """Phase 9B Package 2 replaced exactly two designed tripwires. Not fewer."""
        assert len(TRIPWIRE_REPLACEMENTS) == 2, (
            f"expected exactly 2 tripwire replacements, found "
            f"{len(TRIPWIRE_REPLACEMENTS)}: {TRIPWIRE_REPLACEMENTS}"
        )

    def test_each_replacement_exists_and_asserts_the_obligation(self) -> None:
        for relative, name in TRIPWIRE_REPLACEMENTS:
            path = REPO / relative
            assert path.is_file(), f"{relative} is gone"
            found = [
                node
                for node in ast.walk(tree_of(path))
                if isinstance(node, ast.FunctionDef) and node.name == name
            ]
            assert len(found) == 1, f"{relative}::{name} is missing or duplicated"
            asserted = [
                ast.unparse(node)
                for node in ast.walk(found[0])
                if isinstance(node, ast.Assert)
            ]
            assert asserted, f"{relative}::{name} asserts nothing"
            assert any("NOT_CONFIGURED" in text for text in asserted), (
                f"{relative}::{name} no longer asserts that reaching the "
                "activation phase alone yields NOT_CONFIGURED; the retired "
                "tripwire's obligation has been dropped"
            )

    def test_no_replacement_still_expects_the_retired_refusal(self) -> None:
        """The obligation moved; it did not simply keep the old assertion.

        The docstring is exempted deliberately: explaining what a replacement
        superseded is documentation, and only the executable BODY deciding the
        test's outcome is the subject here.
        """
        for relative, name in TRIPWIRE_REPLACEMENTS:
            found = next(
                node
                for node in ast.walk(tree_of(REPO / relative))
                if isinstance(node, ast.FunctionDef) and node.name == name
            )
            body = [
                stmt for stmt in found.body
                if not (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                )
            ]
            assert body, f"{relative}::{name} has no executable body"
            rendered = "\n".join(ast.unparse(stmt) for stmt in body)
            assert "PrematureActivation" not in rendered, (
                f"{relative}::{name} still expects the retired refusal"
            )


class TestPreActivationStateIsPreserved:
    """Package 1 delivers resolution. It does not report activation success."""

    def _node(self) -> CapabilityNode:
        return CapabilityNode(id="build.compile", version=1, isolation_tier="TRUST-0")

    def _graph(self, current: str) -> CapabilityGraph:
        return CapabilityGraph(
            [self._node()], activation_phase="9B", current_phase=current
        )

    def test_the_query_still_answers_not_configured_before_activation(self) -> None:
        result = self._graph("8").can_perform("build.compile")
        assert result.state is HonestState.NOT_CONFIGURED
        assert result.is_determinate

    def test_an_uncomposed_graph_at_the_activation_phase_invents_no_verdict(
        self,
    ) -> None:
        """REPLACES this module's own Package 1 tripwire, strengthened.

        Package 1 asserted `PrematureActivation` here because no verdict existed
        to compose. Package 2 composes one, so the obligation moves rather than
        disappearing: the phase alone must never produce an affirmative answer,
        because a graph with no composed authority has nothing to derive from.
        """
        result = self._graph("9B").can_perform("build.compile")
        assert result.state is HonestState.NOT_CONFIGURED
        assert result.state is not HonestState.PASS

    def test_explicit_activation_is_still_refused_at_every_phase(self) -> None:
        """There is no flag to set, so the operation refuses at 9B too."""
        for phase in ("8", "9B"):
            with pytest.raises(PrematureActivation):
                self._graph(phase).activate()

    def test_activation_state_remains_a_derived_phase_fact(self) -> None:
        graph = self._graph("8")
        assert graph.is_activated is False
        with pytest.raises(AttributeError):
            graph.is_activated = True  # type: ignore[misc]

    def test_no_stored_activation_flag_was_introduced(self) -> None:
        held = set(vars(self._graph("8")))
        for name in held:
            assert "activated" not in name.lower(), (
                f"{name!r} looks like a stored activation flag; activation is a "
                "phase fact, never a boolean a caller can set"
            )
