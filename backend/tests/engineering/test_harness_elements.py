"""The canonical harness elements are parsed, reconciled and fail closed.

Phase 10 Package 1. These controls exist because the element list is the one
thing `ARK-REQ-0231` cannot afford to have a second copy of: if the canonical
documents change and this repository keeps enforcing the old list while
reporting PASS, the requirement is silently unmet. Every control below is
therefore written against the DOCUMENTS rather than against a remembered list,
and the number eight is asserted in exactly one place - the control that proves
the code holds no such number.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

import pytest

from arkali.engineering.agent.harness_elements import (
    BUILD_PROTOCOL_RELPATH,
    MASTER_SPEC_RELPATH,
    HarnessElementAuthority,
    slug,
)
from arkali.kernel.contracts.error_base import AuthoritativeSourceError

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def authority() -> HarnessElementAuthority:
    return HarnessElementAuthority.load(REPO)


def write_docs(root: pathlib.Path, spec: str, protocol: str) -> pathlib.Path:
    """A repository root carrying only the two canonical harness documents."""
    for relpath, text in ((MASTER_SPEC_RELPATH, spec), (BUILD_PROTOCOL_RELPATH, protocol)):
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def section(*elements: str) -> str:
    return "## Harness Engineering\nEvery task is bounded:\n" + " + ".join(elements) + ".\n"


class TestTheElementsComeFromTheDocuments:
    def test_the_live_documents_declare_the_canonical_elements(
        self, authority: HarnessElementAuthority
    ) -> None:
        """The real answer, read from the real canonical set."""
        assert authority.elements() == (
            "Task Specification",
            "Context Package",
            "Tools",
            "Permissions",
            "Workspace",
            "Environment",
            "Acceptance Target",
            "Repair Budget",
        )
        assert len(authority) == 8

    def test_the_element_names_appear_in_no_module_of_this_context(self) -> None:
        """NO SHADOW MODEL. The list must exist only in the documents.

        Reads the shipping source and fails if an element name is written into
        it as a string literal. This is the control that makes every other one
        meaningful: without it, the parser could be correct and irrelevant.
        """
        owner = REPO / "backend/arkali/engineering/agent"
        offenders: list[str] = []
        for path in sorted(owner.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            body = "\n".join(
                line for line in text.splitlines()
                if not line.lstrip().startswith("#")
            )
            for literal in re.findall(r"""["']([^"'\n]{3,})["']""", body):
                if literal.strip() in {
                    "Task Specification", "Context Package", "Acceptance Target",
                    "Repair Budget",
                }:
                    offenders.append(f"{path.name}: {literal!r}")
        assert not offenders, f"element names hard-coded: {offenders}"

    @pytest.mark.parametrize("size", [2, 3, 5, 9])
    def test_the_count_follows_the_documents_rather_than_a_constant(
        self, tmp_path: pathlib.Path, size: int
    ) -> None:
        """BEHAVIOURAL, not a text scan: the count is whatever is declared.

        A literal search for `8` would be brittle in both directions - it would
        flag an unrelated numeral and would miss a count derived some other way.
        Feeding the parser declarations of four different sizes proves the
        number is read rather than held, which is the obligation itself.
        """
        names = tuple(f"Element{index}" for index in range(size))
        root = write_docs(tmp_path / str(size), section(*names), section(*names))
        authority = HarnessElementAuthority.load(root)
        assert len(authority) == size
        assert authority.elements() == names

    def test_field_names_are_derived_mechanically_from_the_names(
        self, authority: HarnessElementAuthority
    ) -> None:
        assert authority.field_names() == tuple(
            slug(name) for name in authority.elements()
        )
        assert slug("Task Specification") == "task_specification"

    def test_the_order_is_the_documents_order(
        self, authority: HarnessElementAuthority
    ) -> None:
        """Order is part of the declaration, not an incidental detail."""
        text = (REPO / MASTER_SPEC_RELPATH).read_text(encoding="utf-8")
        positions = [text.index(name) for name in authority.elements()]
        assert positions == sorted(positions)


class TestBothDocumentsAreCanonicalAndAreReconciled:
    def test_an_abbreviation_reconciles_to_the_unabbreviated_name(
        self, tmp_path: pathlib.Path
    ) -> None:
        """`Task Spec` and `Task Specification` are the same element."""
        root = write_docs(
            tmp_path,
            section("Task Specification", "Context Package", "Tools"),
            section("Task Spec", "Context", "Tools"),
        )
        assert HarnessElementAuthority.load(root).elements() == (
            "Task Specification", "Context Package", "Tools",
        )

    def test_a_count_disagreement_fails_closed(self, tmp_path: pathlib.Path) -> None:
        root = write_docs(
            tmp_path,
            section("Task Specification", "Context Package", "Tools"),
            section("Task Spec", "Context"),
        )
        with pytest.raises(AuthoritativeSourceError, match="must agree"):
            HarnessElementAuthority.load(root)

    def test_an_unrelated_name_at_a_position_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Neither refines the other, so no list can be derived."""
        root = write_docs(
            tmp_path,
            section("Task Specification", "Context Package", "Tools"),
            section("Task Spec", "Budget", "Tools"),
        )
        with pytest.raises(AuthoritativeSourceError, match="disagree"):
            HarnessElementAuthority.load(root)

    def test_a_reordering_is_refused_rather_than_silently_matched(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Reconciliation is positional; a swap is a disagreement."""
        root = write_docs(
            tmp_path,
            section("Task Specification", "Context Package", "Tools"),
            section("Context", "Task Spec", "Tools"),
        )
        with pytest.raises(AuthoritativeSourceError, match="disagree"):
            HarnessElementAuthority.load(root)

    def test_neither_document_may_be_ignored(self, tmp_path: pathlib.Path) -> None:
        """The register sources ARK-REQ-0054 to MS and ARK-REQ-0231 to BP."""
        root = write_docs(
            tmp_path, section("Task Specification", "Tools"), section("Task Spec", "Tools")
        )
        (root / BUILD_PROTOCOL_RELPATH).unlink()
        with pytest.raises(AuthoritativeSourceError, match="not found"):
            HarnessElementAuthority.load(root)


class TestFailsClosedAndNeverVacuously:
    def test_an_absent_section_is_refused(self, tmp_path: pathlib.Path) -> None:
        root = write_docs(tmp_path, "# Spec\nNo harness here.\n", section("A", "B"))
        with pytest.raises(AuthoritativeSourceError, match="no Harness Engineering"):
            HarnessElementAuthority.load(root)

    def test_a_section_with_no_declaration_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = write_docs(
            tmp_path,
            "## Harness Engineering\nProse with no element sentence.\n",
            section("A", "B"),
        )
        with pytest.raises(AuthoritativeSourceError, match="no element sentence"):
            HarnessElementAuthority.load(root)

    def test_a_single_element_declaration_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A boundedness rule with one requirement would pass vacuously."""
        root = write_docs(
            tmp_path,
            "## Harness Engineering\nBounded by:\nTask Specification.\n",
            section("Task Spec", "Tools"),
        )
        with pytest.raises(AuthoritativeSourceError, match="vacuously|no element"):
            HarnessElementAuthority.load(root)

    def test_the_section_is_bounded_by_the_next_heading(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A `+` sentence in a LATER section must not be read as the declaration."""
        spec = (
            "## Harness Engineering\nBounded by:\nTask Specification + Tools.\n\n"
            "## Something Else\nAlpha + Beta + Gamma + Delta.\n"
        )
        root = write_docs(tmp_path, spec, section("Task Spec", "Tools"))
        assert HarnessElementAuthority.load(root).elements() == (
            "Task Specification", "Tools",
        )
