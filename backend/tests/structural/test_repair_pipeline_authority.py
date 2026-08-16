"""The executable Phase 14 pipeline is a receipted PATH, not a 13th state
machine, and creates no second candidate/evidence/acceptance/policy/release
authority (ARK-REQ-0086, ARK-REQ-0238, D-024).
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PIPELINE: Final[pathlib.Path] = REPO / "backend/arkali/engineering/repair/pipeline.py"
STATE_MACHINES_DOC: Final[pathlib.Path] = REPO / "docs/canonical/STATE_MACHINES.md"

FORBIDDEN_IMPORT_PREFIXES: Final[tuple[str, ...]] = (
    "arkali.lifecycle.",
    "arkali.acceptance.",
    "arkali.control.registry.",
    "arkali.engineering.candidate.",
)


class TestTheStateMachineCountIsUnchanged:
    def test_exactly_twelve_canonical_machines_are_still_declared(self) -> None:
        """Derived from the document, not a remembered number (F-0013)."""
        text = STATE_MACHINES_DOC.read_text(encoding="utf-8")
        headings = re.findall(r"^###\s+\d+\.\s+.+$", text, re.MULTILINE)
        assert len(headings) == 12, headings

    def test_no_repair_or_failure_protocol_machine_was_added(self) -> None:
        text = STATE_MACHINES_DOC.read_text(encoding="utf-8")
        assert "Repair" not in text
        assert "Failure Protocol" not in text


class TestThePipelineImportsNoForeignAuthority:
    def test_pipeline_py_imports_no_forbidden_authority(self) -> None:
        tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    offenders.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                        offenders.append(alias.name)
        assert not offenders, f"forbidden authority imported: {offenders}"

    def test_pipeline_py_defines_no_stable_write_promotion_or_rollback_operation(
        self,
    ) -> None:
        tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
        watched = ("promote", "rollback", "write_stable", "stable_write", "accept_candidate")
        offenders = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(term in node.name.lower() for term in watched)
        ]
        assert not offenders, f"a release/Stable/acceptance operation is defined: {offenders}"

    def test_pipeline_py_performs_no_filesystem_or_process_io(self) -> None:
        """No transformer execution engine exists; this module is receipted
        bookkeeping only, matching docs/contracts/repair.md's boundary."""
        text = PIPELINE.read_text(encoding="utf-8")
        for token in ("open(", "subprocess", "os.system", "shutil.", ".write_bytes", ".write_text"):
            assert token not in text, token
