"""F-0028 — the dependency-direction gate must consume the declared rules.

`AUTHORITY_MAP.yaml` `dependency_rules` declares two exceptions to the layer
direction rule, and `ARCHITECTURE.md` section 4 states the same two in prose:

  rule 5  every context may WRITE to `evidence.*`   -> evidence_write_from_any_layer
  rule 6  `control.policy` is callable from every layer -> policy_callable_from_any_layer

The gate previously implemented layer rank plus `allowed_sibling_edges` only,
and `AuthorityMap` did not parse the section at all, so both exceptions were
rejected. These controls prove the executable gate now agrees with the canonical
declaration, that ordinary upward and same-layer edges are still refused, that
no sibling edge was added to make that true, and that toggling a rule in the map
changes the verdict with no edit to any validator.

No canonical repository file is written by any test here. Gate-level controls
run against an isolated tree under `tmp_path`.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.base import GateContext
from arkali.control.architecture.gates.structure_gates import (
    ForbiddenDependencyDirectionGate,
)
from arkali.kernel.contracts.errors import AuthoritativeSourceError
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]

#: Edges the canonical set permits by exception rather than by layer rank.
EXEMPT_EDGES = (
    ("kernel.persistence", "control.policy"),
    ("control.registry.project", "control.policy"),
    ("surfaces.command", "control.policy"),
    ("kernel.persistence", "evidence.audit"),
    ("kernel.contracts", "evidence.artifact"),
)

#: Edges no rule permits. Upward without an exception, or same layer with no
#: declared sibling edge.
FORBIDDEN_EDGES = (
    ("kernel.persistence", "control.registry.project"),
    ("kernel.persistence", "control.isolation"),
    ("control.policy", "control.isolation"),
    ("control.registry.project", "control.capability"),
    ("evidence.audit", "execution.durable"),
    ("lifecycle.release", "surfaces.command"),
    ("kernel.persistence", "acceptance.engine"),
)


@pytest.fixture()
def live_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


def mutate(amap: AuthorityMap, **changes: object) -> AuthorityMap:
    """In-memory mutation only. The repository file is never touched."""
    data = amap.model_dump()
    data.update(changes)
    return AuthorityMap.model_validate(data)


def with_rules(amap: AuthorityMap, **rules: object) -> AuthorityMap:
    merged = dict(amap.dependency_rules)
    merged.update(rules)
    return mutate(amap, dependency_rules=merged)


def build_tree(root: pathlib.Path, amap: AuthorityMap, owner: str,
               imported: str) -> pathlib.Path:
    """An isolated package tree holding exactly one cross-context import."""
    module_root = root / amap.contexts[owner].module_root
    module_root.mkdir(parents=True, exist_ok=True)
    (module_root / "__init__.py").write_text("", encoding="utf-8")
    (module_root / "edge.py").write_text(
        f"import {imported}\n", encoding="utf-8"
    )
    return root


class TestDependencyRulesAreParsed:
    def test_section_is_read_from_the_authority_map(
        self, live_map: AuthorityMap
    ) -> None:
        """The section must be parsed, not ignored. This is the defect itself."""
        raw = yaml.safe_load(
            (REPO / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
        )
        assert live_map.dependency_rules == raw["dependency_rules"]
        assert live_map.dependency_rules

    def test_canonical_exemptions_are_declared(self, live_map: AuthorityMap) -> None:
        assert live_map.dependency_rules["policy_callable_from_any_layer"] is True
        assert live_map.dependency_rules["evidence_write_from_any_layer"] is True


class TestExemptionResolution:
    def test_policy_subject_resolves_to_the_policy_context(
        self, live_map: AuthorityMap
    ) -> None:
        assert "control.policy" in live_map.cross_layer_exempt_contexts()

    def test_evidence_subject_resolves_to_the_evidence_namespace(
        self, live_map: AuthorityMap
    ) -> None:
        exempt = live_map.cross_layer_exempt_contexts()
        assert {"evidence.artifact", "evidence.audit"} <= exempt

    def test_acceptance_engine_is_not_exempt_despite_sharing_the_layer(
        self, live_map: AuthorityMap
    ) -> None:
        """Rule 5 grants the exception to `evidence.*` by name, not to a layer.

        `acceptance.engine` is declared in the `evidence` layer, so a layer-based
        resolution would wrongly exempt it. Rule 5's companion sentence gives it
        a narrower privilege - reading evidence for a verdict - not a write
        exemption from every layer.
        """
        assert live_map.contexts["acceptance.engine"].layer == "evidence"
        assert "acceptance.engine" not in live_map.cross_layer_exempt_contexts()

    def test_only_the_two_declared_subjects_are_exempt(
        self, live_map: AuthorityMap
    ) -> None:
        assert live_map.cross_layer_exempt_contexts() == frozenset(
            {"control.policy", "evidence.artifact", "evidence.audit"}
        )


class TestEdgePermission:
    @pytest.mark.parametrize(("source", "target"), EXEMPT_EDGES)
    def test_canonically_permitted_edges_are_allowed(
        self, live_map: AuthorityMap, source: str, target: str
    ) -> None:
        assert live_map.edge_permitted(source, target)

    @pytest.mark.parametrize(("source", "target"), FORBIDDEN_EDGES)
    def test_ordinary_upward_and_same_layer_edges_remain_forbidden(
        self, live_map: AuthorityMap, source: str, target: str
    ) -> None:
        assert not live_map.edge_permitted(source, target)

    def test_lower_layer_edges_remain_allowed(self, live_map: AuthorityMap) -> None:
        assert live_map.edge_permitted("surfaces.command", "kernel.contracts")
        assert live_map.edge_permitted("lifecycle.recovery", "kernel.persistence")

    def test_declared_sibling_edge_is_still_allowed(
        self, live_map: AuthorityMap
    ) -> None:
        assert live_map.edge_permitted("lifecycle.recovery", "lifecycle.release")

    def test_reverse_of_a_sibling_edge_is_not_allowed(
        self, live_map: AuthorityMap
    ) -> None:
        assert not live_map.edge_permitted("lifecycle.release", "lifecycle.recovery")


class TestNoNewSiblingEdgeWasIntroduced:
    def test_sibling_edges_match_the_authority_map_exactly(
        self, live_map: AuthorityMap
    ) -> None:
        """The repair must not have widened the architecture to fit the code."""
        raw = yaml.safe_load(
            (REPO / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
        )
        declared = {(e["from"], e["to"]) for e in raw["allowed_sibling_edges"]}
        assert {(e.source, e.target) for e in live_map.sibling_edges} == declared
        assert len(declared) == 7

    def test_no_sibling_edge_targets_an_exempt_context(
        self, live_map: AuthorityMap
    ) -> None:
        exempt = live_map.cross_layer_exempt_contexts()
        assert not {e.target for e in live_map.sibling_edges} & exempt


class TestRuleDrift:
    """Toggling a rule in the map must change the verdict with no code edit."""

    def test_disabling_the_policy_rule_forbids_the_edge(
        self, live_map: AuthorityMap
    ) -> None:
        assert live_map.edge_permitted("kernel.persistence", "control.policy")
        narrowed = with_rules(live_map, policy_callable_from_any_layer=False)
        assert not narrowed.edge_permitted("kernel.persistence", "control.policy")

    def test_disabling_the_evidence_rule_forbids_the_edge(
        self, live_map: AuthorityMap
    ) -> None:
        assert live_map.edge_permitted("kernel.persistence", "evidence.audit")
        narrowed = with_rules(live_map, evidence_write_from_any_layer=False)
        assert not narrowed.edge_permitted("kernel.persistence", "evidence.audit")

    def test_a_new_exemption_key_is_honoured_without_touching_the_validator(
        self, live_map: AuthorityMap
    ) -> None:
        """Generality: the subject is read from the key, not from a known list."""
        assert not live_map.edge_permitted(
            "kernel.persistence", "control.specification"
        )
        widened = with_rules(live_map, specification_callable_from_any_layer=True)
        assert widened.edge_permitted("kernel.persistence", "control.specification")

    def test_disabling_lower_layer_forbids_a_downward_edge(
        self, live_map: AuthorityMap
    ) -> None:
        narrowed = with_rules(live_map, allow_lower_layer=False)
        assert not narrowed.edge_permitted("surfaces.command", "kernel.contracts")

    def test_enabling_same_layer_permits_an_undeclared_sibling(
        self, live_map: AuthorityMap
    ) -> None:
        widened = with_rules(live_map, allow_same_layer=True)
        assert widened.edge_permitted("control.policy", "control.isolation")

    def test_an_omitted_rule_does_not_widen_the_architecture(
        self, live_map: AuthorityMap
    ) -> None:
        """Defaults are the strict reading: omission must never grant."""
        emptied = mutate(live_map, dependency_rules={})
        assert not emptied.edge_permitted("surfaces.command", "kernel.contracts")
        assert not emptied.edge_permitted("kernel.persistence", "control.policy")


class TestFailClosed:
    def test_enabled_rule_with_an_unresolvable_subject_raises(
        self, live_map: AuthorityMap
    ) -> None:
        broken = with_rules(live_map, unicorn_callable_from_any_layer=True)
        with pytest.raises(AuthoritativeSourceError) as exc:
            broken.cross_layer_exempt_contexts()
        assert "unicorn" in str(exc.value)

    def test_a_disabled_unresolvable_rule_is_ignored(
        self, live_map: AuthorityMap
    ) -> None:
        quiet = with_rules(live_map, unicorn_callable_from_any_layer=False)
        assert quiet.cross_layer_exempt_contexts() == (
            live_map.cross_layer_exempt_contexts()
        )

    def test_non_exemption_keys_are_not_treated_as_subjects(
        self, live_map: AuthorityMap
    ) -> None:
        """`evidence_read_for_verdict_only_by` is a read rule, not an exemption.

        It constrains who may read evidence *for a verdict* - a semantic the
        import graph cannot express - so this gate does not consume it, and it
        must not be mistaken for a cross-layer grant.
        """
        assert "evidence_read_for_verdict_only_by" in live_map.dependency_rules
        assert AuthorityMap._exemption_subject("evidence_read_for_verdict_only_by") is None
        assert AuthorityMap._exemption_subject("allow_higher_layer") is None


class TestGateConsumesTheRules:
    def test_live_repository_passes(self, live_map: AuthorityMap) -> None:
        result = ForbiddenDependencyDirectionGate().evaluate(
            GateContext(REPO, live_map)
        )
        assert result.state is HonestState.PASS

    def test_live_repository_uses_no_exempt_edge(
        self, live_map: AuthorityMap
    ) -> None:
        """The repair must not be concealing a real violation in current code."""
        narrowed = with_rules(
            live_map,
            policy_callable_from_any_layer=False,
            evidence_write_from_any_layer=False,
        )
        result = ForbiddenDependencyDirectionGate().evaluate(
            GateContext(REPO, narrowed)
        )
        assert result.state is HonestState.PASS

    def test_gate_accepts_an_exempt_edge_in_an_isolated_tree(
        self, live_map: AuthorityMap, tmp_path: pathlib.Path
    ) -> None:
        root = build_tree(tmp_path, live_map, "kernel.persistence",
                          "arkali.control.policy.pdp")
        result = ForbiddenDependencyDirectionGate().evaluate(
            GateContext(root, live_map)
        )
        assert result.state is HonestState.PASS

    def test_gate_rejects_the_same_edge_when_the_rule_is_disabled(
        self, live_map: AuthorityMap, tmp_path: pathlib.Path
    ) -> None:
        """The verdict follows the map, proving the gate reads it."""
        root = build_tree(tmp_path, live_map, "kernel.persistence",
                          "arkali.control.policy.pdp")
        narrowed = with_rules(live_map, policy_callable_from_any_layer=False)
        result = ForbiddenDependencyDirectionGate().evaluate(
            GateContext(root, narrowed)
        )
        assert result.state is HonestState.FAIL
        assert result.findings

    def test_gate_still_rejects_an_ordinary_upward_edge(
        self, live_map: AuthorityMap, tmp_path: pathlib.Path
    ) -> None:
        root = build_tree(tmp_path, live_map, "kernel.persistence",
                          "arkali.control.registry.project")
        result = ForbiddenDependencyDirectionGate().evaluate(
            GateContext(root, live_map)
        )
        assert result.state is HonestState.FAIL

    def test_gate_still_rejects_an_undeclared_same_layer_edge(
        self, live_map: AuthorityMap, tmp_path: pathlib.Path
    ) -> None:
        root = build_tree(tmp_path, live_map, "control.policy",
                          "arkali.control.isolation.isolation_contract")
        result = ForbiddenDependencyDirectionGate().evaluate(
            GateContext(root, live_map)
        )
        assert result.state is HonestState.FAIL


class TestCanonicalStateUnmodified:
    def test_authority_map_is_not_written(self, live_map: AuthorityMap) -> None:
        path = REPO / "docs" / "canonical" / "AUTHORITY_MAP.yaml"
        before = path.read_bytes()
        with_rules(live_map, policy_callable_from_any_layer=False)
        ForbiddenDependencyDirectionGate().evaluate(GateContext(REPO, live_map))
        assert path.read_bytes() == before
