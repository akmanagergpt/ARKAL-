"""The canonical graph set and Digital Twin views are parsed, and fail closed.

Phase 11 Package 1. `ARK-REQ-0066` requires "the specified graph set" and
`ARK-REQ-0067` "the nine specified views" - both phrased as references to a
specification rather than as lists, so the lists must live in the specification
and nowhere else. These controls prove that, and prove the vocabulary refuses
rather than defaults when the specification cannot be read.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

import pytest

from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.codeintel.errors import UnknownGraphKind, UnknownTwinView
from arkali.engineering.codeintel.graph_vocabulary import (
    ARCHITECTURE_RELPATH,
    GraphVocabulary,
    slug,
)
from arkali.kernel.contracts.error_base import AuthoritativeSourceError

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
OWNER: Final[pathlib.Path] = REPO / "backend/arkali/engineering/codeintel"
#: The requirement whose text names how many views the twin composes.
VIEW_COUNT_REQUIREMENT: Final[str] = "ARK-REQ-0067"

_NUMBER_WORDS: Final[dict[str, int]] = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


@pytest.fixture(scope="module")
def vocabulary() -> GraphVocabulary:
    return GraphVocabulary.load(REPO)


def write_architecture(root: pathlib.Path, body: str) -> pathlib.Path:
    target = root / ARCHITECTURE_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return root


def listed(*names: str) -> str:
    return ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]


def section(graphs: tuple[str, ...], views: tuple[str, ...]) -> str:
    return (
        "## 11. Code Intelligence / Digital Twin architecture\n\n"
        f"`engineering.codeintel` maintains {listed(*graphs)} graphs for Python. "
        f"The Digital Twin composes: {', '.join(views)}. It is a derived store.\n"
    )


class TestTheVocabularyComesFromTheArchitecture:
    def test_the_live_document_declares_the_canonical_graph_set(
        self, vocabulary: GraphVocabulary
    ) -> None:
        assert vocabulary.graphs() == (
            "symbol", "import", "dependency", "route", "model", "frontend-contract",
        )

    def test_the_live_document_declares_the_canonical_view_set(
        self, vocabulary: GraphVocabulary
    ) -> None:
        assert vocabulary.view_ids() == (
            "specification", "architecture", "code", "data", "runtime",
            "deployment", "test", "version", "failure",
        )

    def test_the_architecture_and_the_register_agree_on_the_view_count(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """The one cross-document check this phase actually owes.

        `ARK-REQ-0067` says "the nine specified views". The number lives in the
        REGISTER's requirement text and the views live in the ARCHITECTURE, so
        the two could drift apart with neither document looking wrong on its own.
        Both are read here and required to agree - and the number is taken from
        the register rather than written into this control, so a canonical set
        that grows to ten moves this test instead of expiring it.
        """
        statement = RequirementRegister.load(REPO).get(VIEW_COUNT_REQUIREMENT).statement
        words = [w for w in re.split(r"\W+", statement.lower()) if w in _NUMBER_WORDS]
        assert words, f"{VIEW_COUNT_REQUIREMENT} states no view count: {statement!r}"
        assert _NUMBER_WORDS[words[0]] == len(vocabulary.views())

    def test_no_module_of_this_context_hard_codes_a_name(self) -> None:
        """NO SHADOW MODEL. Without this the parser could be correct and unused."""
        governed = {"frontend-contract", "deployment graph", "failure view",
                    "specification view"}
        offenders: list[str] = []
        for path in sorted(OWNER.rglob("*.py")):
            body = "\n".join(
                line for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            )
            code = body.split('"""')[-1]
            offenders.extend(f"{path.name}: {n}" for n in governed if n in code)
        assert not offenders, f"canonical names hard-coded: {offenders}"

    @pytest.mark.parametrize("graphs,views", [(2, 2), (3, 5), (4, 11)])
    def test_both_counts_follow_the_document_rather_than_constants(
        self, tmp_path: pathlib.Path, graphs: int, views: int
    ) -> None:
        """BEHAVIOURAL: the number nine is nowhere in the shipping source."""
        g = tuple(f"kind{i}" for i in range(graphs))
        v = tuple(f"view{i} view" for i in range(views))
        loaded = GraphVocabulary.load(
            write_architecture(tmp_path / f"{graphs}-{views}", section(g, v))
        )
        assert len(loaded.graphs()) == graphs
        assert len(loaded.views()) == views

    def test_the_presentation_suffix_is_not_part_of_the_identity(self) -> None:
        """§11 writes `test view` and `code graph` in the same list."""
        assert slug("test view") == "test"
        assert slug("code graph") == "code"
        assert slug("frontend-contract") == "frontend_contract"


class TestUnknownEntriesAreRefused:
    def test_a_canonical_graph_kind_resolves(
        self, vocabulary: GraphVocabulary
    ) -> None:
        for name in vocabulary.graphs():
            assert vocabulary.require_graph(name) == slug(name)

    def test_a_canonical_view_resolves(self, vocabulary: GraphVocabulary) -> None:
        for name in vocabulary.views():
            assert vocabulary.require_view(name) == slug(name)

    def test_an_unspecified_graph_kind_is_refused(
        self, vocabulary: GraphVocabulary
    ) -> None:
        with pytest.raises(UnknownGraphKind, match="not a canonical graph kind"):
            vocabulary.require_graph("gossip")

    def test_an_unspecified_view_is_refused(
        self, vocabulary: GraphVocabulary
    ) -> None:
        with pytest.raises(UnknownTwinView, match="not a canonical Digital Twin"):
            vocabulary.require_view("vibes")

    def test_the_refusal_names_what_is_specified(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """A refusal a reader cannot act on is barely a refusal."""
        with pytest.raises(UnknownGraphKind) as raised:
            vocabulary.require_graph("gossip")
        assert vocabulary.graphs()[0] in str(raised.value)

    def test_a_view_name_is_not_accepted_as_a_graph_kind(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """The two vocabularies are distinct even where they read alike."""
        with pytest.raises(UnknownGraphKind):
            vocabulary.require_graph("deployment")


class TestFailsClosedAndNeverVacuously:
    def test_a_missing_document_is_refused(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(AuthoritativeSourceError, match="not found"):
            GraphVocabulary.load(tmp_path)

    def test_an_absent_section_is_refused(self, tmp_path: pathlib.Path) -> None:
        root = write_architecture(tmp_path, "## 1. Something else\n\nProse.\n")
        with pytest.raises(AuthoritativeSourceError, match="no Code Intelligence"):
            GraphVocabulary.load(root)

    def test_a_section_with_no_graph_clause_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        body = (
            "## 11. Code Intelligence / Digital Twin architecture\n\n"
            "The Digital Twin composes: a view, b view. Derived store.\n"
        )
        with pytest.raises(AuthoritativeSourceError, match="no graph set"):
            GraphVocabulary.load(write_architecture(tmp_path, body))

    def test_a_section_with_no_view_clause_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        body = (
            "## 11. Code Intelligence / Digital Twin architecture\n\n"
            "`engineering.codeintel` maintains a and b graphs for Python.\n"
        )
        with pytest.raises(AuthoritativeSourceError, match="no Digital Twin view set"):
            GraphVocabulary.load(write_architecture(tmp_path, body))

    @pytest.mark.parametrize("which", ["graphs", "views"])
    def test_a_single_entry_set_is_refused_as_vacuous(
        self, tmp_path: pathlib.Path, which: str
    ) -> None:
        graphs = ("only",) if which == "graphs" else ("a", "b")
        views = ("only view",) if which == "views" else ("a view", "b view")
        with pytest.raises(AuthoritativeSourceError, match="vacuously"):
            GraphVocabulary.load(
                write_architecture(tmp_path / which, section(graphs, views))
            )

    def test_the_section_is_bounded_by_the_next_heading(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A later section's sentence must not be read as this declaration."""
        body = (
            section(("a", "b"), ("a view", "b view"))
            + "\n## 12. Something else\n\n`x` maintains p, q and r graphs for Rust. "
            "The Digital Twin composes: z view, y view.\n"
        )
        loaded = GraphVocabulary.load(write_architecture(tmp_path, body))
        assert loaded.graphs() == ("a", "b")
        assert loaded.view_ids() == ("a", "b")
