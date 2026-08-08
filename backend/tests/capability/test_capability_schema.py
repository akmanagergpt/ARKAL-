"""C-13 capability node schema verification (ARK-REQ-0045, ARK-REQ-0047).

The node's declared attribute set is checked against the canonical schema in
`docs/canonical/EXECUTION_AND_CAPABILITY.md` §1 by parsing that document, so this
test cannot drift from the contract it verifies.

All fixtures are in-memory. No repository state is written.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml
from arkali.control.capability.capability_graph import CapabilityGraph
from arkali.control.capability.capability_node import (
    CapabilityNode,
    ConfiguredState,
    validate_no_shadow_registry,
)
from arkali.kernel.contracts.capability_errors import (
    DuplicateCapabilityIdentity,
    InvalidCapabilityReference,
    MalformedCapabilityIdentity,
    ShadowRegistryViolation,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_DOC = REPO / "docs/canonical/EXECUTION_AND_CAPABILITY.md"
AUTHORITY_MAP = REPO / "docs/canonical/AUTHORITY_MAP.yaml"


def canonical_node_fields() -> tuple[str, ...]:
    """Field names parsed from the canonical `capability_node:` yaml block."""
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    block = re.search(r"```yaml\s*\ncapability_node:\s*\n(.*?)```", text, re.S)
    assert block is not None, "canonical capability_node schema block not found"
    found = tuple(
        match.group(1)
        for match in re.finditer(r"^\s{2}(\w+):", block.group(1), re.M)
    )
    assert found, "canonical schema block declared no fields"
    return found


def provider_owned_fields() -> tuple[str, ...]:
    raw = yaml.safe_load(AUTHORITY_MAP.read_text(encoding="utf-8"))
    owned = tuple(raw["provider_authority"]["fields_owned"])
    assert owned, "authority map declares no provider-owned fields"
    return owned


def node(**overrides: object) -> CapabilityNode:
    base: dict[str, object] = {
        "id": "build.compile",
        "version": 1,
        "isolation_tier": "TRUST-2",
    }
    base.update(overrides)
    return CapabilityNode(**base)  # type: ignore[arg-type]


class TestSchemaMatchesTheCanonicalContract:
    def test_declared_fields_match_the_canonical_block(self) -> None:
        assert set(CapabilityNode.model_fields) == set(canonical_node_fields())

    def test_no_undeclared_attribute_can_be_attached(self) -> None:
        with pytest.raises(Exception):
            node(health="HEALTHY")

    def test_node_is_immutable(self) -> None:
        with pytest.raises(Exception):
            node().id = "other.capability"  # type: ignore[misc]

    def test_configured_state_defaults_to_unconfigured(self) -> None:
        assert node().configured_state is ConfiguredState.UNCONFIGURED


class TestIdentityValidation:
    @pytest.mark.parametrize(
        "bad_id",
        ["", "Build.Compile", "build compile", "1build", ".build", "build..compile"],
    )
    def test_malformed_identity_is_rejected(self, bad_id: str) -> None:
        with pytest.raises(MalformedCapabilityIdentity):
            node(id=bad_id)

    def test_well_formed_identity_is_accepted(self) -> None:
        assert node(id="engineering.repair.apply_patch").id

    @pytest.mark.parametrize("bad_version", [0, -1])
    def test_non_positive_version_is_rejected(self, bad_version: int) -> None:
        with pytest.raises(MalformedCapabilityIdentity):
            node(version=bad_version)

    @pytest.mark.parametrize("bad_tier", ["TRUST-5", "TRUST", "trust-1", "TIER-1", ""])
    def test_invalid_isolation_tier_is_rejected(self, bad_tier: str) -> None:
        with pytest.raises(MalformedCapabilityIdentity):
            node(isolation_tier=bad_tier)

    @pytest.mark.parametrize("tier", ["TRUST-0", "TRUST-1", "TRUST-4"])
    def test_declared_tiers_are_accepted(self, tier: str) -> None:
        assert node(isolation_tier=tier).isolation_tier == tier

    def test_self_reference_is_rejected(self) -> None:
        with pytest.raises(MalformedCapabilityIdentity):
            node(prerequisites=("build.compile",))

    def test_malformed_reference_is_rejected(self) -> None:
        with pytest.raises(MalformedCapabilityIdentity):
            node(fallback_refs=("Not A Capability",))


class TestShadowRegistryRejection:
    def test_provider_owned_state_in_runtime_requirements_is_rejected(self) -> None:
        for field in provider_owned_fields():
            candidate = node(runtime_requirements={field: "SOME_VALUE"})
            with pytest.raises(ShadowRegistryViolation):
                validate_no_shadow_registry(candidate, provider_owned_fields())

    def test_provider_prefixed_key_is_also_rejected(self) -> None:
        candidate = node(runtime_requirements={"provider_health": "HEALTHY"})
        with pytest.raises(ShadowRegistryViolation):
            validate_no_shadow_registry(candidate, provider_owned_fields())

    def test_legitimate_runtime_requirement_is_accepted(self) -> None:
        candidate = node(runtime_requirements={"min_memory_mb": 512})
        validate_no_shadow_registry(candidate, provider_owned_fields())

    def test_empty_vocabulary_fails_closed_rather_than_vacuously_passing(self) -> None:
        """A check with nothing to compare against must not report PASS."""
        with pytest.raises(ShadowRegistryViolation):
            validate_no_shadow_registry(node(), ())

    def test_the_schema_has_no_provider_state_field_at_all(self) -> None:
        """Structural: provider state cannot be stored even by a willing caller."""
        declared = {name.lower() for name in CapabilityNode.model_fields}
        for owned in provider_owned_fields():
            assert owned.lower() not in declared

    def test_provider_is_referenced_not_copied(self) -> None:
        assert "provider_refs" in CapabilityNode.model_fields
        assert node(provider_refs=("anthropic.claude",)).provider_refs


class TestGraphIntegrity:
    def test_duplicate_identity_is_rejected(self) -> None:
        with pytest.raises(DuplicateCapabilityIdentity):
            CapabilityGraph(
                [node(), node()], activation_phase="9B", current_phase="3"
            )

    def test_unresolved_prerequisite_is_rejected(self) -> None:
        with pytest.raises(InvalidCapabilityReference):
            CapabilityGraph(
                [node(prerequisites=("does.not.exist",))],
                activation_phase="9B",
                current_phase="3",
            )

    def test_unresolved_fallback_is_rejected(self) -> None:
        with pytest.raises(InvalidCapabilityReference):
            CapabilityGraph(
                [node(fallback_refs=("does.not.exist",))],
                activation_phase="9B",
                current_phase="3",
            )

    def test_resolvable_references_are_accepted(self) -> None:
        graph = CapabilityGraph(
            [node(id="build.base"), node(id="build.compile", prerequisites=("build.base",))],
            activation_phase="9B",
            current_phase="3",
        )
        assert graph.ids() == ("build.base", "build.compile")

    def test_unknown_capability_lookup_is_rejected(self) -> None:
        graph = CapabilityGraph([node()], activation_phase="9B", current_phase="3")
        with pytest.raises(InvalidCapabilityReference):
            graph.get("no.such.capability")
