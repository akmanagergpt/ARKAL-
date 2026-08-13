"""C-16 Package 1 traceability and fail-closed controls."""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import update

from arkali.acceptance.evidence_graph import evidence_graph
from arkali.evidence.audit.chain import EvidenceInput
from arkali.evidence.audit.integrity import digest_of
from arkali.evidence.audit.records import AuditRecord
from tests.evidence.plane_harness import critical_provenance

REPO = pathlib.Path(__file__).resolve().parents[3]
pytest_plugins = ("tests.evidence.plane_harness",)


def append_path(plane: object, requirement_id: str = "ARK-REQ-0069") -> AuditRecord:
    artifact_id = plane.artifacts.register(  # type: ignore[attr-defined]
        b"phase-13 evidence graph", critical_provenance()
    )
    return plane.evidence.append(  # type: ignore[attr-defined]
        EvidenceInput(
            requirement_id=requirement_id,
            contract_id="C-16",
            artifact_id=artifact_id,
            test_id="backend/tests/acceptance/test_evidence_graph.py::traceability",
            producer="acceptance.engine",
            result="PASS",
        )
    )


class TestCanonicalVocabulary:
    def test_path_is_parsed_from_the_c16_authority(self) -> None:
        assert evidence_graph.canonical_path(REPO) == (
            "Requirement", "Contract", "Artifact", "Test", "Evidence", "Result"
        )

    def test_missing_or_vacuous_declaration_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        inventory = tmp_path / "docs/canonical"
        inventory.mkdir(parents=True)
        (inventory / "CONTRACT_INVENTORY.md").write_text(
            "| C-16 | Evidence graph edge (`REQ→REQ→`) | `acceptance.engine` | "
            "producers | consumers | GRAPH | path | semver | STRICT | tests | 13 |",
            encoding="utf-8",
        )
        (tmp_path / "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md").write_text(
            "Evidence Graph links REQ→REQ→→Result.", encoding="utf-8"
        )
        with pytest.raises(Exception, match="absent or unparseable|vacuous"):
            evidence_graph.canonical_path(tmp_path)


class TestDerivedGraph:
    def test_complete_traceability_path_is_derived_from_real_c15(
        self, plane: object
    ) -> None:
        with plane.session() as opened:  # type: ignore[attr-defined]
            record = append_path(opened)
        with plane.session() as reopened:  # type: ignore[attr-defined]
            graph = evidence_graph.derive(reopened.evidence, REPO)

        assert graph.chain_head == record.record_hash
        assert tuple(node.kind for node in graph.nodes) == evidence_graph.canonical_path(REPO)
        assert tuple(node.reference for node in graph.nodes) == (
            "ARK-REQ-0069",
            "C-16",
            record.artifact_id,
            "backend/tests/acceptance/test_evidence_graph.py::traceability",
            record.record_hash,
            "PASS",
        )
        assert len(graph.edges) == 5
        assert graph.paths == (graph.nodes,)
        assert all(
            edge.source == graph.nodes[index]
            and edge.target == graph.nodes[index + 1]
            for index, edge in enumerate(graph.edges)
        )

    def test_empty_chain_is_not_a_graph(self, plane: object) -> None:
        with plane.session() as opened:  # type: ignore[attr-defined]
            with pytest.raises(evidence_graph.Refusal, match="empty evidence chain"):
                evidence_graph.derive(opened.evidence, REPO)

    def test_incomplete_path_is_refused(self, plane: object) -> None:
        with plane.session() as opened:  # type: ignore[attr-defined]
            artifact_id = opened.artifacts.register(
                b"incomplete", critical_provenance()
            )
            opened.evidence.append(
                EvidenceInput(
                    requirement_id="ARK-REQ-0069",
                    artifact_id=artifact_id,
                    producer="acceptance.engine",
                    result="PASS",
                )
            )
            with pytest.raises(evidence_graph.Refusal, match="missing nodes"):
                evidence_graph.derive(opened.evidence, REPO)

    def test_corrupt_chain_cannot_be_rendered_as_traceability(self, plane: object) -> None:
        with plane.session() as opened:  # type: ignore[attr-defined]
            record = append_path(opened)
            original_hash = record.record_hash
            opened.session.execute(
                update(AuditRecord)
                .where(AuditRecord.record_hash == original_hash)
                .values(result="FAIL")
            )
            opened.session.expire_all()
            changed = opened.evidence.require(original_hash)
            assert digest_of(changed) != original_hash
            with pytest.raises(evidence_graph.Refusal, match="chain is corrupt"):
                evidence_graph.derive(opened.evidence, REPO)

    def test_superseded_history_is_preserved_not_silently_resolved(
        self, plane: object
    ) -> None:
        with plane.session() as opened:  # type: ignore[attr-defined]
            first = append_path(opened)
            opened.evidence.append(
                EvidenceInput(
                    requirement_id=first.requirement_id,
                    contract_id=first.contract_id,
                    artifact_id=first.artifact_id,
                    test_id=first.test_id,
                    producer="independent.reviewer",
                    result="FAIL",
                    supersedes=first.record_hash,
                )
            )
            graph = evidence_graph.derive(opened.evidence, REPO)
        results = [node.reference for node in graph.nodes if node.kind == "Result"]
        assert results == ["PASS", "FAIL"]
        assert len(graph.paths) == 2
