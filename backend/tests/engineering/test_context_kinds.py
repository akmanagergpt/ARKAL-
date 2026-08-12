"""The admissible context kinds are parsed and fail closed (ARK-REQ-0055).

Phase 10 Package 2. "Only relevant context" is only meaningful if the definition
of relevant comes from the canonical document. These controls prove the
vocabulary is read rather than held, and that a document which declares nothing
is refused instead of admitting everything.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

import pytest

from arkali.engineering.agent.context_kinds import (
    MASTER_SPEC_RELPATH,
    ContextKindAuthority,
    slug,
)
from arkali.kernel.contracts.error_base import AuthoritativeSourceError

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


def write_spec(root: pathlib.Path, body: str) -> pathlib.Path:
    target = root / MASTER_SPEC_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return root


def section(*kinds: str) -> str:
    listed = ", ".join(kinds[:-1]) + f" and {kinds[-1]}" if len(kinds) > 1 else kinds[0]
    return (
        f"## Context Compiler\nARKALI sends only relevant {listed} to a model. "
        "Context provenance is recorded.\n"
    )


class TestTheVocabularyComesFromTheDocument:
    def test_the_live_document_declares_the_canonical_kinds(self) -> None:
        authority = ContextKindAuthority.load(REPO)
        assert authority.kinds() == (
            "files", "symbols", "contracts", "tests", "ADRs", "failures",
            "verified knowledge",
        )

    @pytest.mark.parametrize("size", [2, 3, 5])
    def test_the_count_follows_the_document_rather_than_a_constant(
        self, tmp_path: pathlib.Path, size: int
    ) -> None:
        """BEHAVIOURAL: feed it different vocabularies and it reports each."""
        names = tuple(f"kind{index}" for index in range(size))
        root = write_spec(tmp_path / str(size), section(*names))
        authority = ContextKindAuthority.load(root)
        assert len(authority) == size
        assert authority.kinds() == names

    def test_the_kind_names_appear_in_no_module_of_this_context(self) -> None:
        """NO SHADOW MODEL. Without this, the parser could be irrelevant."""
        owner = REPO / "backend/arkali/engineering/agent"
        governed = {"verified knowledge", "ADRs"}
        offenders: list[str] = []
        for path in sorted(owner.rglob("*.py")):
            body = "\n".join(
                line for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            )
            for literal in re.findall(r"""["']([^"'\n]{3,})["']""", body):
                if literal.strip() in governed:
                    offenders.append(f"{path.name}: {literal!r}")
        assert not offenders, f"kind names hard-coded: {offenders}"

    def test_identifiers_are_derived_mechanically(self) -> None:
        authority = ContextKindAuthority.load(REPO)
        assert authority.identifiers() == tuple(slug(k) for k in authority.kinds())
        assert slug("verified knowledge") == "verified_knowledge"

    def test_admission_is_a_closed_vocabulary(self) -> None:
        authority = ContextKindAuthority.load(REPO)
        assert authority.admits("files")
        assert authority.admits("Verified Knowledge"), "slug form should match"
        assert not authority.admits("slack messages")


class TestFailsClosedAndNeverVacuously:
    def test_an_absent_section_is_refused(self, tmp_path: pathlib.Path) -> None:
        root = write_spec(tmp_path, "# Spec\nNo compiler section here.\n")
        with pytest.raises(AuthoritativeSourceError, match="no Context Compiler"):
            ContextKindAuthority.load(root)

    def test_a_section_with_no_enumeration_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = write_spec(
            tmp_path, "## Context Compiler\nProvenance is recorded.\n"
        )
        with pytest.raises(AuthoritativeSourceError, match="enumerates no"):
            ContextKindAuthority.load(root)

    def test_a_single_kind_is_refused_as_vacuous(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A relevance rule with nothing to exclude proves nothing."""
        root = write_spec(tmp_path, section("files"))
        with pytest.raises(AuthoritativeSourceError, match="vacuously"):
            ContextKindAuthority.load(root)

    def test_a_missing_document_is_refused(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(AuthoritativeSourceError, match="not found"):
            ContextKindAuthority.load(tmp_path)

    def test_the_section_is_bounded_by_the_next_heading(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An enumeration in a LATER section must not be read as this one."""
        body = (
            section("files", "tests")
            + "\n## Something Else\nARKALI sends only relevant rumours and "
            "gossip to a model.\n"
        )
        root = write_spec(tmp_path, body)
        assert ContextKindAuthority.load(root).kinds() == ("files", "tests")
