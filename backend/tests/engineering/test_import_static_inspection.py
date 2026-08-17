"""Static inspection: no execution, deterministic addressing.

Phase 19 Package 2. ARK-REQ-0115 ("TRUST-3 requires static inspection before
any execution", evidence sec+prop) and ARK-REQ-0161 ("external projects
statically inspected before execution", evidence sec+prop).
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.engineering.project_import.errors import UnverifiedStaticInspectionError
from arkali.engineering.project_import.static_inspection import StaticInspector

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]

#: A file whose only defect is a side effect at *import time*. If anything in
#: the inspection path ever executed or imported target source, this would
#: create the sentinel file; `ast.parse` never runs module-level statements,
#: so it must not.
_LANDMINE = """\
import pathlib as _pathlib
_pathlib.Path(__file__).with_name("EXECUTED.sentinel").write_text("boom")

def declared_function():
    return 1
"""


@pytest.fixture()
def vocabulary() -> GraphVocabulary:
    return GraphVocabulary.load(REPO)


def _write_project(root: pathlib.Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "landmine.py").write_text(_LANDMINE, encoding="utf-8")
    (root / "plain.py").write_text("import os\n\ndef f():\n    return os.getcwd()\n", encoding="utf-8")
    sub = root / "pkg"
    sub.mkdir()
    (sub / "__init__.py").write_text("", encoding="utf-8")
    (sub / "mod.py").write_text("from .. import plain\n", encoding="utf-8")


class TestNoExecutionOccurs:
    def test_inspecting_a_landmine_never_triggers_its_side_effect(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        project = tmp_path / "external_project"
        _write_project(project)
        sentinel = project / "EXECUTED.sentinel"
        assert not sentinel.exists()

        report = StaticInspector(vocabulary).inspect(project)

        assert not sentinel.exists(), (
            "static inspection executed target source; ARK-REQ-0115 requires "
            "static inspection before any execution"
        )
        assert report.executed is False
        assert report.file_count == 4
        assert set(report.graph_kinds) == {"symbol", "import", "dependency"}


class TestDeterministicAddressing:
    def test_two_inspections_of_identical_content_address_identically(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        first_root = tmp_path / "first"
        second_root = tmp_path / "second"
        _write_project(first_root)
        _write_project(second_root)

        first = StaticInspector(vocabulary).inspect(first_root)
        second = StaticInspector(vocabulary).inspect(second_root)

        assert first.source_address == second.source_address
        assert first.graph_addresses == second.graph_addresses

    def test_changing_one_byte_changes_the_source_address(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        project = tmp_path / "external_project"
        _write_project(project)
        before = StaticInspector(vocabulary).inspect(project)

        (project / "plain.py").write_text(
            "import os\n\ndef f():\n    return os.getcwd() + '!'\n", encoding="utf-8"
        )
        after = StaticInspector(vocabulary).inspect(project)

        assert before.source_address != after.source_address

    def test_address_is_independent_of_filesystem_enumeration_order(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        """Files are written in reverse name order in the second tree; the
        address must not depend on that."""
        forward = tmp_path / "forward"
        reverse = tmp_path / "reverse"
        for root, names in (
            (forward, ("a.py", "m.py", "z.py")),
            (reverse, ("z.py", "m.py", "a.py")),
        ):
            root.mkdir()
            for name in names:
                (root / name).write_text("x = 1\n", encoding="utf-8")

        first = StaticInspector(vocabulary).inspect(forward)
        second = StaticInspector(vocabulary).inspect(reverse)
        assert first.source_address == second.source_address


class TestRefusesAnAbsentRoot:
    def test_a_nonexistent_root_is_refused(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        with pytest.raises(UnverifiedStaticInspectionError):
            StaticInspector(vocabulary).inspect(tmp_path / "does-not-exist")
