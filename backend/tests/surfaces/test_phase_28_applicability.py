"""Mechanical ARK-REQ-0180 applicability evidence after ERR-005."""

from __future__ import annotations

import pathlib

from arkali.control.capability.capability_node import CapabilityNode
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.localai.adapter import (
    HonestState,
    LocalModelDescriptor,
    RuntimeProbeResult,
)
from arkali.engineering.localai.capability_exposure import build_capability_node
from arkali.engineering.localai.suitability import SuitabilityVerdict


REPO = pathlib.Path(__file__).resolve().parents[3]
REQ = "ARK-REQ-0180"


def applicable(node: CapabilityNode) -> bool:
    return node.runtime_requirements.get("local_executable") is True


def test_erratum_path_is_the_live_register_rule() -> None:
    rule = RequirementRegister.load(REPO).applicability_rule(REQ)
    assert rule is not None
    assert "capability.runtime_requirements.local_executable == true" in rule
    assert "ERR-005" in rule


def test_the_only_shipping_capability_constructor_does_not_declare_applicability() -> None:
    descriptor = LocalModelDescriptor(
        runtime="ollama", model_id="local-probe", parameter_size="1B",
        quantization="Q4_0", context_length=1024,
    )
    node = build_capability_node(
        descriptor,
        RuntimeProbeResult(runtime="ollama", state=HonestState.PASS, detail="ready"),
        SuitabilityVerdict(model_id="local-probe", state=HonestState.PASS, reason="fits"),
    )
    assert applicable(node) is False


def test_missing_false_and_non_boolean_values_fail_closed() -> None:
    base = {"id": "probe.local", "version": 1, "isolation_tier": "TRUST-0"}
    for value in (None, False, 1, "true"):
        requirements = {} if value is None else {"local_executable": value}
        assert applicable(CapabilityNode(**base, runtime_requirements=requirements)) is False


def test_the_authorized_nested_boolean_can_make_the_rule_applicable() -> None:
    node = CapabilityNode(
        id="probe.local", version=1, isolation_tier="TRUST-0",
        runtime_requirements={"local_executable": True},
    )
    assert applicable(node) is True

