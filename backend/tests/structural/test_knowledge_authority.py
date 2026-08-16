"""C-28 (`engineering.knowledge`, Phase 18) is an evidence-derived value
contract, not a 13th state machine, not a persistence authority, not a PDP
operation, and not a shadow copy of `engineering.repair`'s evidence
(ARK-REQ-0126, ARK-REQ-0127, ARK-REQ-0128, ARK-REQ-0394).
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
KNOWLEDGE_DIR: Final[pathlib.Path] = REPO / "backend/arkali/engineering/knowledge"
STATE_MACHINES_DOC: Final[pathlib.Path] = REPO / "docs/canonical/STATE_MACHINES.md"
AUTHORITY_MAP: Final[pathlib.Path] = REPO / "docs/canonical/AUTHORITY_MAP.yaml"

MODULES: Final[tuple[pathlib.Path, ...]] = tuple(
    sorted(p for p in KNOWLEDGE_DIR.glob("*.py") if p.name != "__init__.py")
)

#: Layers/authorities `engineering.knowledge` (layer engineering, rank 4)
#: must never import: higher-or-equal-rank engineering siblings it has no
#: declared `allowed_sibling_edges` entry for, persistence (no table is
#: claimed, docs/contracts/knowledge.md §1), policy/PDP (no operation class
#: applies, docs/contracts/knowledge.md §7), and every lifecycle/acceptance/
#: registry authority a value-object contract has no business composing.
FORBIDDEN_IMPORT_PREFIXES: Final[tuple[str, ...]] = (
    "arkali.lifecycle.",
    "arkali.acceptance.",
    "arkali.control.registry.",
    "arkali.control.policy.",
    "arkali.kernel.persistence.",
    "arkali.engineering.repair.",
    "arkali.engineering.factory.",
    "arkali.engineering.candidate.",
    "arkali.engineering.agent.",
    "arkali.evidence.",
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

    def test_no_knowledge_machine_was_added_to_the_canonical_document(self) -> None:
        text = STATE_MACHINES_DOC.read_text(encoding="utf-8")
        assert "Knowledge" not in text


class TestKnowledgeModulesImportNoForbiddenAuthority:
    def test_no_module_imports_a_forbidden_prefix(self) -> None:
        offenders: dict[str, list[str]] = {}
        for module in MODULES:
            bad = [
                name
                for name in _imports(module)
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES)
            ]
            if bad:
                offenders[module.name] = bad
        assert not offenders, offenders

    def test_no_module_imports_pydantic_dependent_state_via_a_pdp_call(self) -> None:
        """No action in this context maps to one of the 14 canonical PDP
        operation classes (docs/contracts/knowledge.md §7); recording a
        value object is not a computer-use action."""
        for module in MODULES:
            text = module.read_text(encoding="utf-8")
            assert "PolicyDecisionPoint" not in text
            assert "PermissionEnforcementPoint" not in text
            assert "OperationClass" not in text

    def test_no_module_performs_filesystem_or_process_io(self) -> None:
        for module in MODULES:
            text = module.read_text(encoding="utf-8")
            tokens = (
                "open(", "subprocess", "os.system", "shutil.",
                ".write_bytes", ".write_text",
            )
            for token in tokens:
                assert token not in text, f"{module.name}: {token}"

    def test_no_module_defines_a_promote_rollback_or_stable_write_operation(self) -> None:
        watched = ("promote", "rollback", "write_stable", "stable_write", "accept_candidate")
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


class TestNoNewUndeclaredSiblingEdgeWasIntroduced:
    def test_engineering_knowledge_still_has_no_allowed_sibling_edges_entry(self) -> None:
        """This package composes evidence generically (`EvidenceReference`)
        rather than importing `engineering.repair`'s concrete
        `RepairFingerprint`/`RepairBudgetLedger` types, so no new
        `allowed_sibling_edges` declaration was required — verified against
        the live map rather than assumed."""
        text = AUTHORITY_MAP.read_text(encoding="utf-8")
        assert "from: engineering.knowledge" not in text
