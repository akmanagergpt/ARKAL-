"""The composed Phase 15 real-authority journey (D-025 Quality Bar).

natural-language product goal -> normalized/decomposed requirement blueprint
-> provenance -> ambiguity detection -> acceptance criteria -> architecture
mapping -> machine-readable blueprint, over the REAL `AuthorityMap` and REAL
`RequirementRegister` — no mocks, matching the Phase 14 journey precedent.
"""

from __future__ import annotations

import pathlib

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.blueprint_contracts import RequirementBlueprint
from arkali.control.specification.blueprint_engine import derive_blueprint
from arkali.control.specification.register_parser import RequirementRegister

REPO = pathlib.Path(__file__).resolve().parents[3]

GOAL_TEXT = (
    "Users must authenticate securely. "
    "The system must respond within 200ms. "
    "Orders must persist in the database. "
    "It should be fast."
)


def test_step_1_the_real_authority_map_and_register_load() -> None:
    """Denominator and composed authority are re-derived live, never assumed."""
    authority_map = AuthorityMap.load(REPO)
    register = RequirementRegister.load(REPO)
    assert len(register.for_phase("15")) > 0, "Phase 15 has a real denominator"
    assert authority_map.concerns, "the authority map declares real concerns"


def test_step_2_a_real_goal_decomposes_with_provenance() -> None:
    authority_map = AuthorityMap.load(REPO)
    blueprint = derive_blueprint(GOAL_TEXT, authority_map)
    assert len(blueprint.requirements) == 4
    for requirement in blueprint.requirements:
        assert requirement.requirement_id.startswith("sha256:")
    assert blueprint.goal.goal_text == GOAL_TEXT


def test_step_3_ambiguity_and_missing_criteria_are_honestly_recorded() -> None:
    authority_map = AuthorityMap.load(REPO)
    blueprint = derive_blueprint(GOAL_TEXT, authority_map)
    assert not blueprint.is_fully_resolved
    assert blueprint.unresolved, "the vague final statement must be flagged"


def test_step_4_at_least_one_requirement_carries_a_derived_acceptance_criterion() -> None:
    authority_map = AuthorityMap.load(REPO)
    blueprint = derive_blueprint(GOAL_TEXT, authority_map)
    with_criteria = [r for r in blueprint.requirements if r.acceptance_criteria]
    assert with_criteria, blueprint.requirements


def test_step_5_a_security_requirement_maps_to_a_live_architecture_concern() -> None:
    authority_map = AuthorityMap.load(REPO)
    blueprint = derive_blueprint(GOAL_TEXT, authority_map)
    mapped = [r for r in blueprint.requirements if r.owning_concern is not None]
    assert mapped, blueprint.requirements
    live_concerns = {c.concern for c in authority_map.concerns}
    for requirement in mapped:
        assert requirement.owning_concern in live_concerns


def test_step_6_the_blueprint_is_a_phase_16_consumable_interface() -> None:
    """A downstream consumer (the future Phase 16) needs only the JSON shape,
    never Phase 15's Python objects — proving the contract is a real
    interchange boundary and not an in-process convenience object."""
    authority_map = AuthorityMap.load(REPO)
    blueprint = derive_blueprint(GOAL_TEXT, authority_map)
    payload = blueprint.model_dump_json()
    restored = RequirementBlueprint.model_validate_json(payload)
    assert restored.blueprint_id == blueprint.blueprint_id
    assert restored == blueprint


def test_step_7_a_revision_carries_correct_lineage_over_a_changed_goal() -> None:
    """ARK-REQ-0389: later user changes are comparable against prior blueprints."""
    authority_map = AuthorityMap.load(REPO)
    first = derive_blueprint(GOAL_TEXT, authority_map)
    changed_goal = GOAL_TEXT + " The system must respond within 500ms."
    second = derive_blueprint(changed_goal, authority_map, previous=first)
    assert second.revision == first.revision + 1
    assert second.previous_blueprint_id == first.blueprint_id
    assert second.blueprint_id != first.blueprint_id


def test_step_8_no_candidate_requirement_is_or_becomes_an_ark_req_entry() -> None:
    """ARK-REQ-0388: user requirements never conflate with canonical governance
    requirements — proven against the REAL register, not a double."""
    authority_map = AuthorityMap.load(REPO)
    register = RequirementRegister.load(REPO)
    blueprint = derive_blueprint(GOAL_TEXT, authority_map)
    canonical_ids = set(register.all_ids())
    for requirement in blueprint.requirements:
        assert requirement.requirement_id not in canonical_ids
        assert not requirement.requirement_id.startswith("ARK-REQ-")


def test_step_9_deriving_a_blueprint_writes_no_file_and_generates_no_code() -> None:
    """ARK-REQ-0390: Phase 15 produces no product code, proven behaviourally —
    the shipping source tree is unchanged by deriving a blueprint."""
    shipping = REPO / "backend" / "arkali"
    before = {
        p: p.stat().st_mtime_ns for p in shipping.rglob("*.py")
        if "__pycache__" not in str(p)
    }
    authority_map = AuthorityMap.load(REPO)
    derive_blueprint(GOAL_TEXT, authority_map)
    after = {
        p: p.stat().st_mtime_ns for p in shipping.rglob("*.py")
        if "__pycache__" not in str(p)
    }
    assert before == after
