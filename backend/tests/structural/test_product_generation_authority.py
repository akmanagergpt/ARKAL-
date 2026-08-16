"""Real deterministic generation composes C-25/C-37; creates no second
acceptance, candidate, or generation authority (ARK-REQ-0233)."""

from __future__ import annotations

import ast
import pathlib
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
GENERATION: Final[pathlib.Path] = (
    REPO / "backend/arkali/engineering/factory/product_generation.py"
)

FORBIDDEN_IMPORT_PREFIXES: Final[tuple[str, ...]] = (
    "arkali.acceptance.",
    "arkali.lifecycle.",
    "arkali.control.registry.provider.",
)


def _tree() -> ast.AST:
    return ast.parse(GENERATION.read_text(encoding="utf-8"), filename=str(GENERATION))


class TestNoAcceptanceOrReleaseAuthorityIsImported:
    def test_no_forbidden_authority_is_imported(self) -> None:
        offenders: list[str] = []
        for node in ast.walk(_tree()):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    offenders.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                        offenders.append(alias.name)
        assert not offenders, f"forbidden authority imported: {offenders}"


class TestNoAcceptanceVerdictIsRendered:
    def test_generated_product_carries_no_pass_fail_field(self) -> None:
        text = GENERATION.read_text(encoding="utf-8")
        section = text.split("class GeneratedProduct")[1].split("\nclass ")[0]
        for token in ("PASS", "FAIL", "verdict", "accepted: bool"):
            assert token not in section, token


class TestNoFakeSuccessMarkers:
    def test_the_module_writes_only_through_the_real_workspace_authority(self) -> None:
        """No direct filesystem I/O of its own — every write goes through the
        real, reused `CandidateWorkspace.write`, confined to its own root."""
        text = GENERATION.read_text(encoding="utf-8")
        for token in ("open(", "pathlib.Path(", ".write_bytes(", ".write_text("):
            assert token not in text, token
