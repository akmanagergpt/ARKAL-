"""The C-37 blueprint engine creates no second architecture, acceptance or
candidate/product-generation authority (ARK-REQ-0386, ARK-REQ-0390, ARK-REQ-0391,
D-025)."""

from __future__ import annotations

import ast
import pathlib
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
SPEC_DIR: Final[pathlib.Path] = REPO / "backend/arkali/control/specification"
BLUEPRINT_MODULES: Final[tuple[pathlib.Path, ...]] = (
    SPEC_DIR / "blueprint_contracts.py",
    SPEC_DIR / "blueprint_engine.py",
    SPEC_DIR / "blueprint_errors.py",
)

#: `ARK-REQ-0390`/`0391`: no product-generation, candidate-write or
#: acceptance authority may be imported by the blueprint engine.
FORBIDDEN_IMPORT_PREFIXES: Final[tuple[str, ...]] = (
    "arkali.engineering.factory.",
    "arkali.engineering.candidate.",
    "arkali.acceptance.",
    "arkali.lifecycle.",
)

#: Function-name substrings that would signal a second architecture, candidate
#: or acceptance authority rather than composition of the existing ones.
FORBIDDEN_NAME_TERMS: Final[tuple[str, ...]] = (
    "generate_code", "generate_product", "write_code", "build_product",
    "accept_candidate", "accept_blueprint", "promote", "write_stable",
    "stable_write",
)


def _tree(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class TestNoForeignAuthorityIsImported:
    def test_no_blueprint_module_imports_a_forbidden_authority(self) -> None:
        offenders: list[str] = []
        for path in BLUEPRINT_MODULES:
            tree = _tree(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                        offenders.append(f"{path.name}:{node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                            offenders.append(f"{path.name}:{alias.name}")
        assert not offenders, f"forbidden authority imported: {offenders}"


class TestNoSecondArchitectureAcceptanceOrGenerationAuthorityIsDefined:
    def test_no_blueprint_module_defines_a_forbidden_operation(self) -> None:
        offenders: list[str] = []
        for path in BLUEPRINT_MODULES:
            tree = _tree(path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lowered = node.name.lower()
                    if any(term in lowered for term in FORBIDDEN_NAME_TERMS):
                        offenders.append(f"{path.name}:{node.name}")
        assert not offenders, (
            f"a product-generation/acceptance/promotion operation is defined: "
            f"{offenders}"
        )


class TestNoFilesystemOrProcessIO:
    def test_blueprint_engine_performs_no_filesystem_or_process_io(self) -> None:
        """No product code is written anywhere in this context (`ARK-REQ-0390`);
        the engine is a pure data-derivation function."""
        text = (SPEC_DIR / "blueprint_engine.py").read_text(encoding="utf-8")
        for token in ("open(", "subprocess", "os.system", "shutil.",
                      ".write_bytes", ".write_text"):
            assert token not in text, token


class TestArchitectureCompositionIsLiveNotDuplicated:
    def test_map_architecture_holds_no_category_to_owner_table(self) -> None:
        """`ARK-REQ-0386`: the only fixed data is category/word anchors, never
        a concern's OWNER — every owner returned by the engine must come from
        a live `AuthorityMap.concerns` lookup, not a literal in this file."""
        text = (SPEC_DIR / "blueprint_engine.py").read_text(encoding="utf-8")
        forbidden_owners = (
            "control.policy", "control.capability", "control.registry",
            "engineering.factory", "acceptance.engine", "lifecycle.release",
        )
        for owner in forbidden_owners:
            assert owner not in text, (
                f"a bounded-context owner name {owner!r} is hard-coded; "
                "owners must be resolved live from AuthorityMap.concerns"
            )
