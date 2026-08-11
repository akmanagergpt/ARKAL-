"""Query-time reference resolution for activated C-13 (Phase 9B, Package 1).

Nothing here names a field, an authority or a target kind of its own. Every
subject is derived from the canonical `capability_node:` block in
`docs/canonical/EXECUTION_AND_CAPABILITY.md` §1, so a canonical schema that gains
a reference moves these controls instead of expiring them.

All fixtures are in-memory or under `tmp_path`. No repository state is written.
"""

from __future__ import annotations

import pathlib
import shutil
from typing import get_origin

import pytest
from arkali.control.capability.capability_graph import CapabilityGraph
from arkali.control.capability.capability_node import CapabilityNode
from arkali.control.capability.reference_authority import (
    AUTHORITY_MAP_RELPATH,
    SCHEMA_RELPATH,
    CapabilityReferenceAuthority,
)
from arkali.control.capability.reference_resolution import (
    ReferenceResolvers,
    unresolved,
)
from arkali.kernel.contracts.capability_errors import InvalidCapabilityReference
from arkali.kernel.contracts.error_base import AuthoritativeSourceError
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]

#: The requirement whose Phase column governs when activation happens. Read, not
#: written: the same derivation `test_capability_preactivation.py` already uses.
ACTIVATION_REQUIREMENT = "ARK-REQ-0048"


@pytest.fixture(scope="module")
def authority() -> CapabilityReferenceAuthority:
    return CapabilityReferenceAuthority.load(REPO)


class Spy:
    """A resolver that records every question and can change its answer.

    Counting is the point. Proving nothing is cached needs evidence that the
    AUTHORITY was re-asked, not merely that the caller called twice.
    """

    def __init__(self, answer: bool = True) -> None:
        self.answer = answer
        self.asked: list[str] = []

    def resolves(self, reference: str) -> bool:
        self.asked.append(reference)
        return self.answer


class Known:
    """A resolver that resolves exactly the identifiers it was given."""

    def __init__(self, *known: str) -> None:
        self._known = frozenset(known)
        self.asked: list[str] = []

    def resolves(self, reference: str) -> bool:
        self.asked.append(reference)
        return reference in self._known


def node_with_every_external_reference(
    authority: CapabilityReferenceAuthority,
) -> CapabilityNode:
    """A node carrying one reference in every externally-owned field.

    Built from the canonical binding rather than from a written-out list, so a
    new reference field is exercised the day the canonical schema declares it.
    """
    fields: dict[str, object] = {
        "id": "build.compile",
        "version": 1,
        "isolation_tier": "TRUST-2",
    }
    for binding in authority.external():
        declared = CapabilityNode.model_fields[binding.field].annotation
        reference = f"{binding.target_kind}.one"
        holds_many = get_origin(declared) is tuple
        fields[binding.field] = (reference,) if holds_many else reference
    return CapabilityNode(**fields)  # type: ignore[arg-type]


def every_reference(authority: CapabilityReferenceAuthority) -> tuple[str, ...]:
    return tuple(f"{b.target_kind}.one" for b in authority.external())


def resolvers_for(
    authority: CapabilityReferenceAuthority, answer: bool
) -> tuple[ReferenceResolvers, dict[str, Spy]]:
    spies = {name: Spy(answer) for name in authority.authorities()}
    return ReferenceResolvers(authority, spies), spies


class TestBindingIsDerivedFromTheCanonicalSchema:
    def test_every_declared_reference_field_exists_on_the_node(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        for binding in authority.bindings():
            assert binding.field in CapabilityNode.model_fields

    def test_every_node_ref_field_is_a_declared_reference(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        """The other direction: a `*_ref(s)` field with no binding is a gap."""
        bound = {b.field for b in authority.bindings()}
        suffixed = {
            name
            for name in CapabilityNode.model_fields
            if name.endswith("_ref") or name.endswith("_refs")
        }
        assert suffixed, "the node declares no reference field; control vacuous"
        assert suffixed <= bound

    def test_external_and_graph_internal_are_both_non_empty(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        assert authority.external()
        assert authority.graph_internal()

    def test_graph_internal_references_target_capabilities(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        kinds = {b.target_kind for b in authority.graph_internal()}
        assert kinds == {"capability_id"}

    def test_no_external_authority_is_this_context(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        """An authority resolving its own references would be circular."""
        assert "control.capability" not in authority.authorities()

    def test_an_undeclared_field_is_refused(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        with pytest.raises(AuthoritativeSourceError):
            authority.binding_for("no_such_field")


def _copy_documents(root: pathlib.Path) -> pathlib.Path:
    for relative in (SCHEMA_RELPATH, AUTHORITY_MAP_RELPATH):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    return root


class TestBindingFailsClosed:
    """A binding table that cannot be derived is refused, never defaulted."""

    def test_absent_document_is_refused(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(AuthoritativeSourceError):
            CapabilityReferenceAuthority.load(tmp_path)

    def test_absent_schema_block_is_refused(self, tmp_path: pathlib.Path) -> None:
        root = _copy_documents(tmp_path)
        path = root / SCHEMA_RELPATH
        text = path.read_text(encoding="utf-8").replace("capability_node:", "removed:")
        path.write_text(text, encoding="utf-8")
        with pytest.raises(AuthoritativeSourceError):
            CapabilityReferenceAuthority.load(root)

    def test_a_schema_with_no_external_reference_is_refused(
        self, tmp_path: pathlib.Path, authority: CapabilityReferenceAuthority
    ) -> None:
        """Every arrow removed. A rule with no subject must not report success."""
        root = _copy_documents(tmp_path)
        path = root / SCHEMA_RELPATH
        text = path.read_text(encoding="utf-8")
        for name in authority.authorities():
            text = text.replace(f"# -> {name}", "#")
        path.write_text(text, encoding="utf-8")
        with pytest.raises(AuthoritativeSourceError):
            CapabilityReferenceAuthority.load(root)

    def test_an_authority_the_map_does_not_declare_is_refused(
        self, tmp_path: pathlib.Path, authority: CapabilityReferenceAuthority
    ) -> None:
        root = _copy_documents(tmp_path)
        path = root / SCHEMA_RELPATH
        first = authority.authorities()[0]
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                f"# -> {first}", "# -> control.invented"
            ),
            encoding="utf-8",
        )
        with pytest.raises(AuthoritativeSourceError):
            CapabilityReferenceAuthority.load(root)

    def test_an_authority_map_with_no_context_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = _copy_documents(tmp_path)
        (root / AUTHORITY_MAP_RELPATH).write_text("contexts: {}\n", encoding="utf-8")
        with pytest.raises(AuthoritativeSourceError):
            CapabilityReferenceAuthority.load(root)


class TestResolutionAsksTheOwningAuthority:
    def test_every_external_reference_is_put_to_its_own_authority(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, spies = resolvers_for(authority, answer=True)
        node = node_with_every_external_reference(authority)
        results = subject.resolve(node)
        assert len(results) == len(authority.external())
        for binding in authority.external():
            assert spies[binding.authority].asked == [f"{binding.target_kind}.one"]

    def test_a_live_affirmative_answer_resolves(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, _ = resolvers_for(authority, answer=True)
        results = subject.resolve(node_with_every_external_reference(authority))
        assert results and all(r.resolved for r in results)
        assert not unresolved(results)

    def test_a_refusing_authority_fails_and_is_never_retried_into_success(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, _ = resolvers_for(authority, answer=False)
        results = subject.resolve(node_with_every_external_reference(authority))
        assert results
        assert all(r.state is HonestState.FAIL for r in results)
        assert unresolved(results) == results

    def test_an_unknown_reference_fails_closed(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        """A reference the authority does not declare is never assumed."""
        known = {name: Known() for name in authority.authorities()}
        subject = ReferenceResolvers(authority, known)
        results = subject.resolve(node_with_every_external_reference(authority))
        assert results and not any(r.resolved for r in results)

    def test_the_answer_carries_the_reference_and_never_a_value(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, _ = resolvers_for(authority, answer=True)
        results = subject.resolve(node_with_every_external_reference(authority))
        held = set(every_reference(authority))
        assert {r.reference for r in results} == held
        fields = set(type(results[0]).model_fields)
        assert fields == {
            "field",
            "reference",
            "authority",
            "state",
            "reason",
            "authoritative_source",
        }


class TestMissingAuthorityNeverProducesPass:
    def test_no_resolver_yields_not_configured(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject = ReferenceResolvers(authority, {})
        results = subject.resolve(node_with_every_external_reference(authority))
        assert results, "a node with references must produce outcomes"
        assert all(r.state is HonestState.NOT_CONFIGURED for r in results)
        assert not any(r.resolved for r in results)

    def test_missing_authorities_are_reported_not_defaulted(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        assert ReferenceResolvers(authority, {}).missing_authorities() == (
            authority.authorities()
        )

    def test_a_partial_set_resolves_only_what_it_can(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        first = authority.authorities()[0]
        subject = ReferenceResolvers(authority, {first: Spy(True)})
        results = subject.resolve(node_with_every_external_reference(authority))
        passed = [r for r in results if r.resolved]
        assert passed and all(r.authority == first for r in passed)
        assert subject.missing_authorities() == authority.authorities()[1:]

    def test_a_resolver_for_an_unnamed_authority_is_refused(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        with pytest.raises(AuthoritativeSourceError):
            ReferenceResolvers(authority, {"control.invented": Spy(True)})

    def test_a_declared_reference_the_node_cannot_carry_is_refused(
        self, tmp_path: pathlib.Path, authority: CapabilityReferenceAuthority
    ) -> None:
        """Skipping it would silently stop resolving a real reference."""
        root = _copy_documents(tmp_path)
        path = root / SCHEMA_RELPATH
        first = authority.external()[0]
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                f"  {first.field}:",
                f"  absent_refs: [absent_id]  # -> {first.authority}\n"
                f"  {first.field}:",
            ),
            encoding="utf-8",
        )
        widened = CapabilityReferenceAuthority.load(root)
        assert widened.binding_for("absent_refs").is_external
        subject = ReferenceResolvers(widened, {first.authority: Spy(True)})
        with pytest.raises(AuthoritativeSourceError):
            subject.resolve(node_with_every_external_reference(authority))


class TestDeterminismAndNoCaching:
    def test_the_same_state_produces_the_identical_sequence(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, _ = resolvers_for(authority, answer=True)
        node = node_with_every_external_reference(authority)
        rendered = {
            tuple(r.model_dump_json() for r in subject.resolve(node))
            for _ in range(5)
        }
        assert len(rendered) == 1

    def test_the_field_order_follows_the_canonical_schema(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, _ = resolvers_for(authority, answer=True)
        results = subject.resolve(node_with_every_external_reference(authority))
        assert [r.field for r in results] == [b.field for b in authority.external()]

    def test_every_call_re_asks_every_authority(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, spies = resolvers_for(authority, answer=True)
        node = node_with_every_external_reference(authority)
        for _ in range(3):
            subject.resolve(node)
        for spy in spies.values():
            assert len(spy.asked) == 3, "an answer was reused instead of re-asked"

    def test_a_changed_authority_answer_is_visible_on_the_next_call(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        """Calling twice proves nothing; the answer must actually move."""
        subject, spies = resolvers_for(authority, answer=True)
        node = node_with_every_external_reference(authority)
        assert all(r.resolved for r in subject.resolve(node))
        for spy in spies.values():
            spy.answer = False
        assert not any(r.resolved for r in subject.resolve(node))

    def test_the_resolvers_hold_no_outcome(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        """Structural: two attributes, both supplied, neither an answer."""
        subject, _ = resolvers_for(authority, answer=True)
        subject.resolve(node_with_every_external_reference(authority))
        assert set(vars(subject)) == {"_binding_authority", "_resolvers"}


class TestGraphResolutionAndPreservedPreActivationState:
    def _graph(
        self, authority: CapabilityReferenceAuthority, references: object
    ) -> CapabilityGraph:
        return CapabilityGraph(
            [node_with_every_external_reference(authority)],
            activation_phase="9B",
            current_phase="9B",
            references=references,  # type: ignore[arg-type]
        )

    def test_the_graph_resolves_through_the_composed_authorities(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, spies = resolvers_for(authority, answer=True)
        graph = self._graph(authority, subject)
        results = graph.resolve_references("build.compile")
        assert results and all(r.resolved for r in results)
        assert all(spy.asked for spy in spies.values())

    def test_resolution_without_composed_authorities_refuses(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        """An empty answer would read as 'everything resolved'."""
        with pytest.raises(InvalidCapabilityReference):
            self._graph(authority, None).resolve_references("build.compile")

    def test_an_unknown_capability_still_raises(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, _ = resolvers_for(authority, answer=True)
        with pytest.raises(InvalidCapabilityReference):
            self._graph(authority, subject).resolve_references("no.such.capability")

    def test_the_graph_retains_no_resolution(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, _ = resolvers_for(authority, answer=True)
        graph = self._graph(authority, subject)
        graph.resolve_references("build.compile")
        assert set(vars(graph)) == {
            "_nodes",
            "activation_phase",
            "current_phase",
            "_references",
        }

    def test_resolution_does_not_make_the_query_answer_a_verdict(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        """Package 1 delivers resolution, not activation of `can_perform`.

        The pre-activation answer is unchanged and production admission still
        refuses. Reporting a verdict here would be Package 2's work wearing
        Package 1's name.
        """
        subject, _ = resolvers_for(authority, answer=True)
        graph = CapabilityGraph(
            [node_with_every_external_reference(authority)],
            activation_phase="9B",
            current_phase="8",
            references=subject,
        )
        assert graph.can_perform("build.compile").state is HonestState.NOT_CONFIGURED
        assert all(r.resolved for r in graph.resolve_references("build.compile"))

    def test_a_node_holding_no_external_reference_resolves_nothing(
        self, authority: CapabilityReferenceAuthority
    ) -> None:
        subject, spies = resolvers_for(authority, answer=True)
        graph = CapabilityGraph(
            [CapabilityNode(id="build.bare", version=1, isolation_tier="TRUST-0")],
            activation_phase="9B",
            current_phase="9B",
            references=subject,
        )
        assert graph.resolve_references("build.bare") == ()
        assert not any(spy.asked for spy in spies.values())
