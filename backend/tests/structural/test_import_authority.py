"""C-29 (`engineering.import`, Phase 19) is a descriptor-and-tier-assignment
pipeline that composes existing authorities, not a 13th state machine, not a
persistence authority, not a second copy of `engineering.candidate`'s
workspace mechanism, and not an execution engine (ARK-REQ-0115, 0116, 0161,
0162, 0348).
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
IMPORT_DIR: Final[pathlib.Path] = REPO / "backend/arkali/engineering/project_import"
STATE_MACHINES_DOC: Final[pathlib.Path] = REPO / "docs/canonical/STATE_MACHINES.md"
AUTHORITY_MAP: Final[pathlib.Path] = REPO / "docs/canonical/AUTHORITY_MAP.yaml"
CONTRACT_INVENTORY: Final[pathlib.Path] = REPO / "docs/canonical/CONTRACT_INVENTORY.md"
CONTRACT_DOC: Final[pathlib.Path] = REPO / "docs/contracts/import.md"

MODULES: Final[tuple[pathlib.Path, ...]] = tuple(
    sorted(p for p in IMPORT_DIR.glob("*.py") if p.name != "__init__.py")
)

#: Legitimate reuse points, composed unmodified: control.isolation and
#: control.policy (execution_gate.py), engineering.codeintel (declared
#: sibling edge, static_inspection.py). Everything else this list names is
#: authority a descriptor-and-tier-assignment pipeline has no business
#: composing — persistence (INT, no table), acceptance/lifecycle,
#: registries, and every other engineering sibling.
FORBIDDEN_IMPORT_PREFIXES: Final[tuple[str, ...]] = (
    "arkali.lifecycle.",
    "arkali.acceptance.",
    "arkali.control.registry.",
    "arkali.control.architecture.",
    "arkali.control.specification.",
    "arkali.kernel.persistence.",
    "arkali.engineering.repair.",
    "arkali.engineering.factory.",
    "arkali.engineering.agent.",
    "arkali.engineering.knowledge.",
    "arkali.engineering.plugin.",
    "arkali.evidence.",
    # engineering.candidate is composed only through a structural Protocol
    # (pipeline.py) — a direct import here would extend an already-at-
    # ceiling orchestration chain (docs/contracts/import.md §6).
    "arkali.engineering.candidate.",
)


def _imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


class TestTheStateMachineCountIsUnchanged:
    def test_exactly_twelve_canonical_machines_are_still_declared(self) -> None:
        text = STATE_MACHINES_DOC.read_text(encoding="utf-8")
        headings = re.findall(r"^###\s+\d+\.\s+.+$", text, re.MULTILINE)
        assert len(headings) == 12, headings

    def test_import_project_is_the_existing_twelfth_machine_not_a_new_one(self) -> None:
        text = STATE_MACHINES_DOC.read_text(encoding="utf-8")
        assert "Import Project" in text
        assert text.count("### 12. Import Project") == 1


class TestImportModulesImportNoForbiddenAuthority:
    def test_no_module_imports_a_forbidden_prefix(self) -> None:
        offenders: dict[str, list[str]] = {}
        for module in MODULES:
            bad = [
                name for name in _imports(module)
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES)
            ]
            if bad:
                offenders[module.name] = bad
        assert not offenders, offenders

    def test_no_module_defines_a_repair_modernise_or_rebuild_operation(self) -> None:
        """C-29 selects a rescue mode; it does not execute one
        (docs/contracts/import.md §4, §9)."""
        watched = ("repair_source", "modernise", "modernize", "rebuild_source")
        offenders: list[str] = []
        for module in MODULES:
            tree = ast.parse(module.read_text(encoding="utf-8"))
            offenders.extend(
                f"{module.name}:{node.name}"
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(term in node.name.lower() for term in watched)
            )
        assert not offenders, offenders


class TestNoNewCandidateSiblingEdgeWasIntroduced:
    def test_no_engineering_import_to_candidate_edge_is_declared(self) -> None:
        """The working copy is materialised through a structural `Protocol`
        (pipeline.py), never a direct import, so no new sibling edge was
        required — verified against the live map rather than assumed."""
        text = AUTHORITY_MAP.read_text(encoding="utf-8")
        assert "from: engineering.import, to: engineering.candidate" not in text

    def test_the_codeintel_edge_is_declared_exactly_once(self) -> None:
        text = AUTHORITY_MAP.read_text(encoding="utf-8")
        assert text.count("from: engineering.import, to: engineering.codeintel") == 1


class TestContractDocumentMatchesTheInventory:
    def test_the_contract_document_exists(self) -> None:
        assert CONTRACT_DOC.is_file()

    def test_the_inventory_row_names_this_document(self) -> None:
        inventory = CONTRACT_INVENTORY.read_text(encoding="utf-8")
        row = next(
            (line for line in inventory.splitlines() if line.startswith("| C-29 ")),
            None,
        )
        assert row is not None, "CONTRACT_INVENTORY.md declares no C-29 row"
        assert "docs/contracts/import.md" in row
        assert "engineering.import" in row
        assert "19" in row.split("|")[-2]
