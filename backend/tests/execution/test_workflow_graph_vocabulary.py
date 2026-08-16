"""C-20 canonical node-kind / control-construct vocabulary (Phase 17 Package 1).

REAL DOCUMENT ONLY for the positive path: the live
`docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md` is parsed, not a
fixture standing in for it. Negative controls copy that real document into a
tmp root and mutate the copy, so a refusal here is proven against the same
parser the shipping code runs, not a stand-in that always refuses.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.execution.workflow.errors import (
    CanonicalWorkflowSourceError,
    UnknownControlConstruct,
    UnknownNodeKind,
)
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary

REPO = pathlib.Path(__file__).resolve().parents[3]
VDC_RELPATH = "docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md"


def _copy_vdc(root: pathlib.Path, text: str) -> None:
    target = root / VDC_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


class TestCanonicalVocabularyLoadsFromTheRealDocument:
    def test_ten_node_kinds_in_canonical_order(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        assert vocabulary.node_kinds() == (
            "trigger", "AI", "agent", "engineering", "logic", "data",
            "integration", "approval", "release", "notification",
        )

    def test_ten_control_constructs_in_canonical_order(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        assert vocabulary.control_constructs() == (
            "IF", "ELSE", "SWITCH", "LOOP", "PARALLEL", "MERGE", "WAIT",
            "RETRY", "ERROR HANDLER", "HUMAN APPROVAL",
        )

    def test_require_node_kind_accepts_every_canonical_kind(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        for kind in vocabulary.node_kinds():
            assert vocabulary.require_node_kind(kind) == kind

    def test_require_control_construct_accepts_every_canonical_construct(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        for construct in vocabulary.control_constructs():
            assert vocabulary.require_control_construct(construct) == construct


class TestUnknownDeclarationsAreRefused:
    def test_unknown_node_kind_is_refused_by_type_and_reason(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        with pytest.raises(UnknownNodeKind, match="webhook"):
            vocabulary.require_node_kind("webhook")

    def test_unknown_control_construct_is_refused_by_type_and_reason(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        with pytest.raises(UnknownControlConstruct, match="GOTO"):
            vocabulary.require_control_construct("GOTO")


class TestCanonicalSourceFailsClosed:
    def test_missing_document_refuses(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(CanonicalWorkflowSourceError, match="not found"):
            GraphVocabulary.load(tmp_path)

    def test_missing_section_refuses(self, tmp_path: pathlib.Path) -> None:
        _copy_vdc(tmp_path, "# Verification and Delivery Contract\n\nNo such section.\n")
        with pytest.raises(
            CanonicalWorkflowSourceError, match="Workflow Studio execution identity"
        ):
            GraphVocabulary.load(tmp_path)

    def test_empty_node_kind_list_refuses(self, tmp_path: pathlib.Path) -> None:
        text = (
            "## Workflow Studio execution identity\n"
            "Prove the executor. For every canonical node type — — and every "
            "control construct — IF, ELSE — provide evidence.\n"
        )
        _copy_vdc(tmp_path, text)
        with pytest.raises(CanonicalWorkflowSourceError, match="node type"):
            GraphVocabulary.load(tmp_path)

    def test_duplicated_node_kind_refuses(self, tmp_path: pathlib.Path) -> None:
        text = (
            "## Workflow Studio execution identity\n"
            "Prove the executor. For every canonical node type — trigger, "
            "trigger, logic — and every control construct — IF, ELSE — "
            "provide evidence.\n"
        )
        _copy_vdc(tmp_path, text)
        with pytest.raises(CanonicalWorkflowSourceError, match="repeats"):
            GraphVocabulary.load(tmp_path)

    def test_node_kind_list_without_trigger_refuses(self, tmp_path: pathlib.Path) -> None:
        text = (
            "## Workflow Studio execution identity\n"
            "Prove the executor. For every canonical node type — logic, data "
            "— and every control construct — IF, ELSE — provide evidence.\n"
        )
        _copy_vdc(tmp_path, text)
        with pytest.raises(CanonicalWorkflowSourceError, match="trigger"):
            GraphVocabulary.load(tmp_path)

    def test_node_kind_list_without_logic_refuses(self, tmp_path: pathlib.Path) -> None:
        text = (
            "## Workflow Studio execution identity\n"
            "Prove the executor. For every canonical node type — trigger, "
            "data — and every control construct — IF, ELSE — provide "
            "evidence.\n"
        )
        _copy_vdc(tmp_path, text)
        with pytest.raises(CanonicalWorkflowSourceError, match="logic"):
            GraphVocabulary.load(tmp_path)
