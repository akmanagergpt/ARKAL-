"""Negative controls for the handoff's LIVE architecture summary (F-0047).

F-0046 added seven narrative controls, but every one is a predicate over
GOVERNANCE state. `check_handoff.py` never invoked the architecture mechanism at
all, so no architecture number in the manifest had ever been compared with
anything: the manifest reported 100 cross-context edges while the gates measured
102, and the validator reported PASS.

Each control mutates an IN-MEMORY copy of the manifest text and asserts
detection BY NAME. No repository state is modified. Every mutation is DERIVED
from `architecture_truth`, so none can become correct as the tree grows - the
F-0021 rule that a negative control must not have an expiry date.

ADR-0008 decomposition: `test_handoff_drift.py` reached its 400 logical-line
budget, and the seam is the same one `handoff_architecture.py` splits on. No
GATE 8 exception was requested.
"""

from __future__ import annotations

import re
import types

import pytest

from tests.governance.handoff_harness import (
    HANDOFF,
    REPO,
    drift_names,
    load_architecture,
    load_validator,
    rendered_fan_in,
    replace_once,
)


@pytest.fixture(scope="module")
def validator() -> types.ModuleType:
    return load_validator()


@pytest.fixture(scope="module")
def handoff_text() -> str:
    return HANDOFF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def architecture() -> dict:
    """Live architecture metrics, from the canonical gate mechanism."""
    return load_architecture().architecture_truth(REPO)


class TestArchitectureMetricsAreDerived:
    """Every live architecture figure is compared with the gates that made it."""

    def test_a_stale_edge_count_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        live = architecture["edges"]
        mutated = replace_once(
            handoff_text,
            f"**{live}** real cross-context edges",
            f"**{live + 1}** real cross-context edges",
        )
        assert "cross-context edge count" in drift_names(validator, mutated)

    def test_a_removed_edge_count_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        """ANTI-VACUITY. Deleting the claim must fail, not compare nothing."""
        mutated = replace_once(
            handoff_text, f"**{architecture['edges']}** real cross-context edges", ""
        )
        assert "the live architecture summary still states the cross-context edge count" \
            in drift_names(validator, mutated)

    def test_a_stale_gate_count_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        live = architecture["gates_total"]
        mutated = replace_once(
            handoff_text, f"{live} gates PASS", f"{live + 1} gates PASS"
        )
        assert "architecture gate count" in drift_names(validator, mutated)

    def test_a_false_zero_violation_claim_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        live = architecture["violations"]
        mutated = replace_once(
            handoff_text,
            f"| Architecture violations | **{live}**",
            f"| Architecture violations | **{live + 2}**",
        )
        assert "architecture violation count" in drift_names(validator, mutated)

    def test_a_stale_budget_count_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        live = architecture["budgets_evaluated"]
        mutated = replace_once(
            handoff_text,
            f"**{live}** numeric budgets",
            f"**{live - 1}** numeric budgets",
        )
        assert "numeric budget count" in drift_names(validator, mutated)

    def test_a_stale_measurement_contract_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        mutated = replace_once(
            handoff_text,
            f"ratified contract {architecture['measurement_contract']}",
            "ratified contract 9.9.9",
        )
        assert "budget measurement contract" in drift_names(validator, mutated)

    def test_a_stale_orchestration_depth_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        live, allowed = architecture["depth"], architecture["depth_allowed"]
        mutated = replace_once(
            handoff_text,
            f"`max_orchestration_depth` is {live} of {allowed}",
            f"`max_orchestration_depth` is {live - 1} of {allowed}",
        )
        assert "orchestration depth" in drift_names(validator, mutated)

    def test_a_stale_orchestration_ceiling_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        live, allowed = architecture["depth"], architecture["depth_allowed"]
        mutated = replace_once(
            handoff_text,
            f"`max_orchestration_depth` is {live} of {allowed}",
            f"`max_orchestration_depth` is {live} of {allowed + 1}",
        )
        assert "orchestration depth ceiling" in drift_names(validator, mutated)

    def test_a_stale_orchestration_path_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        live = architecture["depth_path"].replace(" -> ", " → ")
        mutated = replace_once(
            handoff_text, live, " → ".join(reversed(live.split(" → ")))
        )
        assert "orchestration depth path" in drift_names(validator, mutated)

    def test_a_removed_orchestration_path_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        """ANTI-VACUITY, and the reason the search is anchored to the claim: the
        live summary names other import chains, and an unanchored control would
        silently compare one of those instead."""
        mutated = replace_once(
            handoff_text, architecture["depth_path"].replace(" -> ", " → "), "elsewhere"
        )
        assert "the live architecture summary still states the orchestration depth path" \
            in drift_names(validator, mutated)

    def test_a_stale_fan_in_figure_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        claim, measured = rendered_fan_in(architecture)
        mutated = replace_once(
            handoff_text,
            claim,
            claim.replace(f"**{measured} of", f"**{measured - 1} of"),
        )
        assert any(d.startswith("fan-in of ") for d in drift_names(validator, mutated))

    def test_a_stale_fan_in_ceiling_is_detected(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        claim, _ = rendered_fan_in(architecture)
        allowed = architecture["fan_in_allowed"]
        mutated = replace_once(
            handoff_text, claim, claim.replace(f"of {allowed}**", f"of {allowed + 7}**")
        )
        assert any(
            d.startswith("fan-in ceiling for ") for d in drift_names(validator, mutated)
        )

    def test_an_unresolvable_fan_in_subject_fails_closed(
        self, validator: types.ModuleType, handoff_text: str, architecture: dict
    ) -> None:
        """A module nobody can resolve must fail, never be skipped."""
        claim, _ = rendered_fan_in(architecture)
        mutated = replace_once(
            handoff_text, f"`{claim.split('`')[1]}`", "`no.such.module`"
        )
        assert any(
            "resolves to exactly one module" in d for d in drift_names(validator, mutated)
        )

    def test_a_removed_fan_in_claim_is_detected(
        self, validator: types.ModuleType, handoff_text: str
    ) -> None:
        """ANTI-VACUITY over the whole fan-in family."""
        mutated = re.sub(r"`[\w.]+` fan-in is \*\*\d+ of \d+\*\*", "", handoff_text)
        assert "the live architecture summary still states a fan-in figure" in \
            drift_names(validator, mutated)


class TestArchitectureTruthComesFromTheGates:
    """The metrics must be the gates' own, not a second implementation."""

    def test_the_edge_count_is_agreed_by_two_independent_gates(
        self, architecture: dict
    ) -> None:
        assert architecture["edges"] is not None, (
            "the edge count is refused unless the direction gate and the cycle "
            "gate report the same number; None means they disagreed"
        )

    def test_every_declared_gate_runs_and_passes(self, architecture: dict) -> None:
        assert architecture["gates_total"] > 0
        assert architecture["gates_passing"] == architecture["gates_total"]

    def test_fan_in_is_measured_for_real_modules(self, architecture: dict) -> None:
        """The probe must return the gate's own arithmetic, not an empty map."""
        assert architecture["fan_in"], "no module fan-in was measured"
        assert max(architecture["fan_in"].values()) <= architecture["fan_in_allowed"]

    def test_measuring_fan_in_does_not_write_the_authority_map(self) -> None:
        """The probe lowers a budget in memory; the file may not change."""
        source = REPO / "docs" / "canonical" / "AUTHORITY_MAP.yaml"
        before = source.read_bytes()
        load_architecture().architecture_truth(REPO)
        assert source.read_bytes() == before


class TestArchitectureMutationsDoNotDecay:
    """F-0021 guard: every mutation above must still differ from live truth."""

    def test_numeric_mutations_still_differ(self, architecture: dict) -> None:
        assert architecture["edges"] + 1 != architecture["edges"]
        assert architecture["gates_total"] + 1 != architecture["gates_total"]
        assert architecture["budgets_evaluated"] - 1 != architecture["budgets_evaluated"]
        assert architecture["depth"] - 1 != architecture["depth"]
        assert architecture["measurement_contract"] != "9.9.9"

    def test_the_reversed_depth_path_is_a_different_path(
        self, architecture: dict
    ) -> None:
        nodes = architecture["depth_path"].split(" -> ")
        assert len(nodes) > 1, "a one-node path cannot be reversed into a mutation"
        assert list(reversed(nodes)) != nodes
