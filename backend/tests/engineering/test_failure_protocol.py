"""The canonical failure-protocol stages are parsed, and their genuine
count disagreement is proven mechanically rather than assumed.

Phase 14 Package 3. `ARK-REQ-0086` cites MS §Root-Cause; `ARK-REQ-0238` cites
BP §Failure protocol. The register assigns Phase 14 to both, so neither
document may be preferred. These controls exist because a silently invented
reconciliation would be a second, undeclared authority for what the pipeline
is - exactly the alias-table defect `harness_elements.py`'s own docstring
warns against - so this module must be proven to REFUSE the real documents
before anything is built on top of it.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

import pytest

from arkali.engineering.repair.failure_protocol import (
    BUILD_PROTOCOL_RELPATH,
    MASTER_SPEC_RELPATH,
    FailureProtocolVocabulary,
)
from arkali.kernel.contracts.error_base import AuthoritativeSourceError

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def vocabulary() -> FailureProtocolVocabulary:
    return FailureProtocolVocabulary.load(REPO)


def write_docs(root: pathlib.Path, spec: str, protocol: str) -> pathlib.Path:
    """A repository root carrying only the two canonical failure-protocol docs."""
    for relpath, text in ((MASTER_SPEC_RELPATH, spec), (BUILD_PROTOCOL_RELPATH, protocol)):
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def ms_section(*stages: str) -> str:
    return "## Root-Cause and Convergence Engine\n" + "→".join(stages) + ".\n"


def bp_section(*stages: str) -> str:
    return "## Failure protocol\n" + "→".join(stages) + ".\n"


class TestBothDeclarationsComeFromTheDocuments:
    def test_the_live_ms_document_declares_its_nine_stages(
        self, vocabulary: FailureProtocolVocabulary
    ) -> None:
        """The real answer, read from the real Master Specification."""
        assert vocabulary.ms_stages() == (
            "Reproduce", "Observe", "Evidence", "Hypotheses", "Experiment",
            "Root Cause", "Minimal Repair", "Targeted Acceptance", "Regression",
        )

    def test_the_live_bp_document_declares_its_eleven_stages(
        self, vocabulary: FailureProtocolVocabulary
    ) -> None:
        """The real answer, read from the real Build Protocol."""
        assert vocabulary.bp_stages() == (
            "Reproduce", "Evidence", "Classify", "Hypotheses", "Experiment",
            "Root Cause", "Minimal Change", "Candidate", "Targeted Tests",
            "Regression", "Accept/Reject",
        )

    def test_no_stage_name_appears_as_a_python_string_literal_in_this_context(
        self,
    ) -> None:
        """NO SHADOW MODEL. The lists must exist only in the documents.

        Backtick-quoted mentions in prose/docstrings are not Python string
        literals and are excluded, matching `test_harness_elements.py`.
        """
        owner = REPO / "backend/arkali/engineering/repair"
        offenders: list[str] = []
        watched = {"Observe", "Root Cause", "Minimal Repair", "Targeted Acceptance",
                   "Classify", "Minimal Change", "Candidate", "Targeted Tests",
                   "Accept/Reject"}
        for path in sorted(owner.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            body = "\n".join(
                line for line in text.splitlines()
                if not line.lstrip().startswith("#")
            )
            for literal in re.findall(r"""["']([^"'\n]{3,})["']""", body):
                if literal.strip() in watched:
                    offenders.append(f"{path.name}: {literal!r}")
        assert not offenders, f"stage names hard-coded: {offenders}"

    @pytest.mark.parametrize("size", [2, 3, 5, 9])
    def test_the_count_follows_the_documents_rather_than_a_constant(
        self, tmp_path: pathlib.Path, size: int
    ) -> None:
        """BEHAVIOURAL, not a text scan: read whatever is declared."""
        names = tuple(f"Stage{index}" for index in range(size))
        root = write_docs(tmp_path / str(size), ms_section(*names), bp_section(*names))
        vocab = FailureProtocolVocabulary.load(root)
        assert vocab.ms_stages() == names
        assert vocab.bp_stages() == names
        assert vocab.stages() == names

    def test_the_ms_order_is_the_documents_order(
        self, vocabulary: FailureProtocolVocabulary
    ) -> None:
        """Checked within the declaring section: several stage words (e.g.
        `Evidence`, `Regression`) recur elsewhere in the document's prose, so
        a whole-document search would be testing the wrong occurrence."""
        text = (REPO / MASTER_SPEC_RELPATH).read_text(encoding="utf-8")
        section_start = text.index("## Root-Cause and Convergence Engine")
        chain_start = text.index("Reproduce→", section_start)
        positions = [text.index(name, chain_start) for name in vocabulary.ms_stages()]
        assert positions == sorted(positions)


class TestTheRealDocumentsGenuinelyDoNotReconcile:
    def test_stages_refuses_because_the_real_counts_disagree(
        self, vocabulary: FailureProtocolVocabulary
    ) -> None:
        """The honest result: 9 against 11, proven, not assumed.

        This is the control the whole package exists to make possible: it
        proves the ambiguity recorded in `docs/build/DECISION_LOG.md` is real
        and mechanically detected rather than eyeballed from two paragraphs.
        """
        with pytest.raises(AuthoritativeSourceError, match="must agree"):
            vocabulary.stages()

    def test_the_refusal_names_both_declared_counts(
        self, vocabulary: FailureProtocolVocabulary
    ) -> None:
        with pytest.raises(AuthoritativeSourceError, match=r"9 root-cause.*11 failure"):
            vocabulary.stages()


class TestReconciliationAlgorithmIsProvenCorrect:
    """Synthetic fixtures, matching a shared count, exercise the mechanism
    the real documents currently cannot reach."""

    def test_an_abbreviation_reconciles_to_the_unabbreviated_name(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = write_docs(
            tmp_path,
            ms_section("Reproduce", "Root Cause", "Regression"),
            bp_section("Reproduce", "Root", "Regression"),
        )
        assert FailureProtocolVocabulary.load(root).stages() == (
            "Reproduce", "Root Cause", "Regression",
        )

    def test_an_unrelated_name_at_a_position_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = write_docs(
            tmp_path,
            ms_section("Reproduce", "Observe", "Regression"),
            bp_section("Reproduce", "Classify", "Regression"),
        )
        with pytest.raises(AuthoritativeSourceError, match="disagree"):
            FailureProtocolVocabulary.load(root).stages()

    def test_a_reordering_is_refused_rather_than_silently_matched(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = write_docs(
            tmp_path,
            ms_section("Reproduce", "Root Cause", "Regression"),
            bp_section("Root Cause", "Reproduce", "Regression"),
        )
        with pytest.raises(AuthoritativeSourceError, match="disagree"):
            FailureProtocolVocabulary.load(root).stages()

    def test_neither_document_may_be_ignored(self, tmp_path: pathlib.Path) -> None:
        root = write_docs(
            tmp_path,
            ms_section("Reproduce", "Regression"),
            bp_section("Reproduce", "Regression"),
        )
        (root / BUILD_PROTOCOL_RELPATH).unlink()
        with pytest.raises(AuthoritativeSourceError, match="not found"):
            FailureProtocolVocabulary.load(root)


class TestFailsClosedAndNeverVacuously:
    def test_an_absent_ms_section_is_refused(self, tmp_path: pathlib.Path) -> None:
        root = write_docs(
            tmp_path, "# Spec\nNo pipeline here.\n", bp_section("Reproduce", "Regression"),
        )
        with pytest.raises(AuthoritativeSourceError, match="no MS Root-Cause"):
            FailureProtocolVocabulary.load(root)

    def test_an_absent_bp_section_is_refused(self, tmp_path: pathlib.Path) -> None:
        root = write_docs(
            tmp_path, ms_section("Reproduce", "Regression"), "# Protocol\nNo pipeline here.\n",
        )
        with pytest.raises(AuthoritativeSourceError, match="no BP Failure"):
            FailureProtocolVocabulary.load(root)

    def test_a_section_with_no_arrow_chain_is_refused(self, tmp_path: pathlib.Path) -> None:
        root = write_docs(
            tmp_path,
            "## Root-Cause and Convergence Engine\nProse with no chain.\n",
            bp_section("Reproduce", "Regression"),
        )
        with pytest.raises(AuthoritativeSourceError, match="no stage chain"):
            FailureProtocolVocabulary.load(root)

    def test_a_single_stage_chain_is_refused(self, tmp_path: pathlib.Path) -> None:
        """A pipeline with one stage would pass 'followed end to end' vacuously."""
        root = write_docs(
            tmp_path,
            "## Root-Cause and Convergence Engine\nReproduce alone.\n",
            bp_section("Reproduce", "Regression"),
        )
        with pytest.raises(AuthoritativeSourceError, match="no stage chain"):
            FailureProtocolVocabulary.load(root)

    def test_the_section_is_bounded_by_the_next_heading(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An arrow chain in a LATER section must not be read as the declaration."""
        spec = (
            "## Root-Cause and Convergence Engine\nReproduce→Regression.\n\n"
            "## Something Else\nAlpha→Beta→Gamma→Delta.\n"
        )
        root = write_docs(tmp_path, spec, bp_section("Reproduce", "Regression"))
        vocab = FailureProtocolVocabulary.load(root)
        assert vocab.ms_stages() == ("Reproduce", "Regression")
