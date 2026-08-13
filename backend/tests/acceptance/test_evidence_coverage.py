"""Phase 13 Package 2: register-derived applicability and coverage."""

from __future__ import annotations

import pathlib

import pytest

from arkali.acceptance.evidence_coverage import evidence_coverage
from arkali.acceptance.evidence_graph import evidence_graph
from arkali.evidence.audit.chain import EvidenceInput
from tests.evidence.plane_harness import critical_provenance

REPO = pathlib.Path(__file__).resolve().parents[3]
pytest_plugins = ("tests.evidence.plane_harness",)


def append_evidence(plane: object, requirement_id: str, kind: str, result: str) -> None:
    artifact_id = plane.artifacts.register(  # type: ignore[attr-defined]
        f"{requirement_id}:{kind}:{result}".encode(), critical_provenance()
    )
    plane.evidence.append(  # type: ignore[attr-defined]
        EvidenceInput(
            requirement_id=requirement_id,
            contract_id="C-16",
            artifact_id=artifact_id,
            test_id=kind,
            producer="acceptance.engine",
            result=result,
        )
    )


class TestRegisterApplicability:
    def test_mandatory_is_always_applicable(self) -> None:
        answer = evidence_coverage.applicability(REPO, "ARK-REQ-0038", {})
        assert answer.applicable and answer.evaluated and answer.rule is None

    def test_registered_rule_is_evaluated_only_from_recorded_state(self) -> None:
        assert evidence_coverage.applicability(
            REPO, "ARK-REQ-0060", {"job_type.supports_pause": True}
        ).applicable
        assert not evidence_coverage.applicability(
            REPO, "ARK-REQ-0060", {"job_type.supports_pause": False}
        ).applicable

    def test_unevaluable_rule_resolves_to_applicable(self) -> None:
        answer = evidence_coverage.applicability(REPO, "ARK-REQ-0060", {})
        assert answer.applicable and not answer.evaluated

    def test_compound_and_reference_rules_use_recorded_state(self) -> None:
        answer = evidence_coverage.applicability(
            REPO,
            "ARK-REQ-0130",
            {
                "isolation.probe.local_ai_runtime_available": False,
                "hardware.probe.accelerator_present": True,
                "dataset.verified_count": 2,
            },
        )
        assert not answer.applicable and answer.evaluated

    def test_set_fallback_and_dimension_rules_are_objective(self) -> None:
        assert evidence_coverage.applicability(
            REPO, "ARK-REQ-0084", {"component.kind": "parser"}
        ).applicable
        assert not evidence_coverage.applicability(
            REPO,
            "ARK-REQ-0084",
            {"component.kind": "ordinary", "fuzz_target": False},
        ).applicable
        assert not evidence_coverage.applicability(
            REPO,
            "ARK-REQ-0356",
            {
                "hardware.probe.gpu_available": False,
                "hardware.probe.vram_available": False,
                "provider.registry.primary.cost_reporting": False,
            },
        ).applicable

    def test_unregistered_claim_is_a_failure(self) -> None:
        with pytest.raises(Exception, match="unknown requirement"):
            evidence_coverage.applicability(REPO, "ARK-REQ-9999", {})


class TestGraphCoverage:
    def test_denominator_and_evidence_are_register_derived(self, plane: object) -> None:
        with plane.session() as opened:  # type: ignore[attr-defined]
            append_evidence(opened, "ARK-REQ-0069", "integ", "PASS")
            append_evidence(opened, "ARK-REQ-0069", "prov", "PASS")
            append_evidence(opened, "ARK-REQ-0037", "arch", "FAIL")
            graph = evidence_graph.derive(opened.evidence, REPO)
            coverage = evidence_coverage.compute(graph, REPO, {})

        rows = {row.requirement_id: row for row in coverage.requirements}
        assert coverage.requirement_denominator == 311
        assert coverage.requirement_numerator == 1
        assert rows["ARK-REQ-0069"].required_evidence == ("integ", "prov")
        assert rows["ARK-REQ-0069"].present_evidence == ("integ", "prov")
        assert not rows["ARK-REQ-0037"].passed

    def test_non_pass_results_never_count(self, plane: object) -> None:
        with plane.session() as opened:  # type: ignore[attr-defined]
            append_evidence(opened, "ARK-REQ-0069", "integ", "NOT_CONFIGURED")
            graph = evidence_graph.derive(opened.evidence, REPO)
            coverage = evidence_coverage.compute(graph, REPO, {})
        row = next(
            item for item in coverage.requirements
            if item.requirement_id == "ARK-REQ-0069"
        )
        assert not row.passed and row.present_evidence == ()

    def test_false_conditional_is_removed_from_denominator(self, plane: object) -> None:
        with plane.session() as opened:  # type: ignore[attr-defined]
            append_evidence(opened, "ARK-REQ-0069", "integ", "PASS")
            graph = evidence_graph.derive(opened.evidence, REPO)
            coverage = evidence_coverage.compute(
                graph, REPO, {"job_type.supports_pause": False}
            )
        ids = {row.requirement_id for row in coverage.requirements}
        assert "ARK-REQ-0060" not in ids
        assert coverage.requirement_denominator == 310
