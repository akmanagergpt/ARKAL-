"""No `lifecycle.evolution` module other than `child_product_promotion.py`
(and `child_product_version.py`'s own internal `restore_to`) can ever
advance a `ChildProductVersionLineage` with new content (ARK-REQ-0132,
ARK-REQ-0358). Mirrors `test_self_evolution_no_direct_mutation.py`'s
AST-based idiom: the property is that a *call* to the mutating method
cannot be expressed outside its sanctioned sites, not that a docstring
says so.

COLLISION RISK, STATED HONESTLY. `append` is a common method name (plain
`list.append` included); this scan cannot distinguish a call on a real
`ChildProductVersionLineage` from a call on an unrelated list by name
alone. Proven clean today - zero other `.append(` calls exist anywhere in
`lifecycle/evolution` (verified directly before writing this control) -
but a future module adding an ordinary list inside this same directory
would trip this test and need an explicit exemption, the same
premise-scoped-check family `OPEN_BLOCKERS.md` F-0037 already documents
for an unrelated control. Not fixed proactively: inventing an exemption
mechanism before a real case exists would be exactly the "no premature
surface" defect this codebase's own discipline refuses elsewhere.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
EVOLUTION_DIR: Final[pathlib.Path] = REPO / "backend/arkali/lifecycle/evolution"
MUTATING_METHODS: Final[frozenset[str]] = frozenset({"append"})
#: The only two modules ever allowed to call `.append(` in this context.
SOLE_PROMOTER: Final[str] = "child_product_promotion.py"
LINEAGE_OWNER: Final[str] = "child_product_version.py"


def _evolution_modules() -> tuple[pathlib.Path, ...]:
    return tuple(
        sorted(p for p in EVOLUTION_DIR.glob("*.py") if p.name != "__init__.py")
    )


def _called_method_names(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


class TestOnlyPromotionReachesTheRealLineageAdvance:
    def test_this_context_has_the_modules_this_scan_expects(self) -> None:
        names = {p.name for p in _evolution_modules()}
        assert SOLE_PROMOTER in names, names
        assert LINEAGE_OWNER in names, names

    def test_no_module_but_promotion_and_the_lineage_owner_calls_append(self) -> None:
        offenders = []
        for path in _evolution_modules():
            if path.name in (SOLE_PROMOTER, LINEAGE_OWNER):
                continue
            called = _called_method_names(path.read_text(encoding="utf-8"))
            hit = called & MUTATING_METHODS
            if hit:
                offenders.append((path.name, sorted(hit)))
        assert not offenders, f"unexpected lineage-advancing call: {offenders}"

    def test_promotion_calls_append_exactly_where_expected(self) -> None:
        source = (EVOLUTION_DIR / SOLE_PROMOTER).read_text(encoding="utf-8")
        assert "append" in _called_method_names(source)

    def test_no_evolution_module_performs_file_or_process_io_of_its_own(self) -> None:
        """This context orchestrates already-independent authorities; it
        opens no file and starts no process itself (mirrors
        `test_self_evolution_no_direct_mutation.py`'s identical control)."""
        for path in _evolution_modules():
            text = path.read_text(encoding="utf-8")
            for token in (
                "open(", "subprocess", "os.system", "os.replace", "os.remove",
                "shutil.", ".write_bytes(", ".write_text(",
            ):
                assert token not in text, f"{path.name}: {token}"
