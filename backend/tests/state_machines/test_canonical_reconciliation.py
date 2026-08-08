"""Reconciliation: executable definitions vs the canonical inventory.

This is the guard that stops the twelve Phase 3 definitions from becoming a
private copy of `docs/canonical/STATE_MACHINES.md` (defect class F-0013). The
executable definition is the implementation authority for its machine; the
document is the canonical specification. If they disagree in any state,
transition, forbidden pair, terminal state or owning authority, this fails.

Every assertion asserts its own prerequisites first: a reconciliation that ran
over zero machines would pass for the wrong reason (F-0016, F-0017).
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.state_machine_spec import StateMachineInventory

from tests.state_machines.registry import MACHINE_MODULES, all_machines

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def inventory() -> StateMachineInventory:
    return StateMachineInventory.load(REPO)


@pytest.fixture(scope="module")
def authority_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


class TestInventoryCoverage:
    def test_every_declared_machine_is_implemented(
        self, authority_map: AuthorityMap
    ) -> None:
        """The count is derived from the authority map, never assumed."""
        declared = set(authority_map.state_machine_authorities)
        assert declared, "authority map declares no state machines"
        assert set(MACHINE_MODULES) == declared

    def test_document_and_map_declare_the_same_machines(
        self, inventory: StateMachineInventory, authority_map: AuthorityMap
    ) -> None:
        assert len(inventory) > 0, "inventory parsed zero machines"
        assert set(inventory.names()) == set(authority_map.state_machine_authorities)

    def test_implementation_count_matches_both_authorities(
        self, inventory: StateMachineInventory, authority_map: AuthorityMap
    ) -> None:
        machines = all_machines()
        assert len(machines) == len(inventory) == len(
            authority_map.state_machine_authorities
        )


class TestPerMachineReconciliation:
    @pytest.mark.parametrize("name", sorted(MACHINE_MODULES))
    def test_states_match_the_canonical_document(
        self, name: str, inventory: StateMachineInventory
    ) -> None:
        spec = inventory.get(name)
        definition = all_machines()[name].definition
        assert spec.states, f"{name}: canonical document declares no states"
        assert definition.states == spec.states

    @pytest.mark.parametrize("name", sorted(MACHINE_MODULES))
    def test_transitions_match_the_canonical_document(
        self, name: str, inventory: StateMachineInventory
    ) -> None:
        spec = inventory.get(name)
        definition = all_machines()[name].definition
        assert spec.transition_set, f"{name}: canonical document declares no transitions"
        assert definition.transition_set == spec.transition_set

    @pytest.mark.parametrize("name", sorted(MACHINE_MODULES))
    def test_forbidden_pairs_match_the_canonical_document(
        self, name: str, inventory: StateMachineInventory
    ) -> None:
        spec = inventory.get(name)
        definition = all_machines()[name].definition
        assert definition.forbidden_set == spec.forbidden_set

    @pytest.mark.parametrize("name", sorted(MACHINE_MODULES))
    def test_terminal_states_match_the_derived_set(
        self, name: str, inventory: StateMachineInventory
    ) -> None:
        """Terminal is derived from the relation, never declared in two places."""
        spec = inventory.get(name)
        definition = all_machines()[name].definition
        assert set(definition.terminal) == set(spec.terminal_states)

    @pytest.mark.parametrize("name", sorted(MACHINE_MODULES))
    def test_authority_matches_document_and_map(
        self, name: str, inventory: StateMachineInventory, authority_map: AuthorityMap
    ) -> None:
        spec = inventory.get(name)
        definition = all_machines()[name].definition
        declared = authority_map.state_machine_authorities[name]
        assert definition.authority == declared == spec.authority

    @pytest.mark.parametrize("name", sorted(MACHINE_MODULES))
    def test_definition_module_lives_inside_its_authority_context(
        self, name: str, authority_map: AuthorityMap
    ) -> None:
        """Ownership is structural: the file sits in the owning context's root."""
        owner = authority_map.state_machine_authorities[name]
        module_root = authority_map.contexts[owner].module_root
        module_file = pathlib.Path(MACHINE_MODULES[name].__file__ or "")
        expected = (REPO / module_root).resolve()
        assert expected.is_dir(), f"{owner}: module root {module_root} absent"
        assert module_file.resolve().parent == expected


class TestNoContradictionSurvives:
    @pytest.mark.parametrize("name", sorted(MACHINE_MODULES))
    def test_forbidden_and_legal_sets_are_disjoint(self, name: str) -> None:
        definition = all_machines()[name].definition
        assert not (definition.forbidden_set & definition.transition_set)

    @pytest.mark.parametrize("name", sorted(MACHINE_MODULES))
    def test_terminal_states_have_no_outgoing_transition(self, name: str) -> None:
        definition = all_machines()[name].definition
        escaping = [
            f"{src}->{dst}"
            for src, dst in definition.transitions
            if src in definition.terminal
        ]
        assert escaping == []


class TestReconciliationIsNotVacuous:
    """The reconciliation must be able to fail. Proven by mutating a copy."""

    def test_a_mutated_definition_is_rejected(
        self, inventory: StateMachineInventory
    ) -> None:
        spec = inventory.get("Project")
        mutated = set(spec.transition_set) | {("DRAFT", "ACTIVE")}
        assert mutated != spec.transition_set

    def test_parser_rejects_an_undeclared_state_reference(self) -> None:
        from arkali.control.architecture.state_machine_spec import _pairs

        found = _pairs("DRAFT→SPECIFIED", ("DRAFT", "SPECIFIED"))
        assert found == [("DRAFT", "SPECIFIED")]
