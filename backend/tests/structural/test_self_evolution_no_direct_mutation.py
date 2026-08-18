"""No `lifecycle.evolution` module other than `core_promotion.py` can ever
reach a real Stable mutation, and `core_promotion.py` itself never reaches
rollback (ARK-REQ-0134, ARK-REQ-0359).

Mirrors `test_repair_pipeline_authority.py`'s AST-based idiom: the property
is that a *call* to a mutating method cannot be expressed outside its one
sanctioned site, not that a docstring says so.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
EVOLUTION_DIR: Final[pathlib.Path] = REPO / "backend/arkali/lifecycle/evolution"
#: The only two methods that ever mutate the Stable-revision pointer.
MUTATING_METHODS: Final[frozenset[str]] = frozenset({"promote", "rollback_to"})
#: The one module in this context allowed to call `.promote(` at all.
SOLE_PROMOTER: Final[str] = "core_promotion.py"


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


class TestOnlyCorePromotionReachesTheRealMutation:
    def test_this_context_has_the_modules_this_scan_expects(self) -> None:
        """Fails loudly if a new module is added and nobody widens the scan."""
        names = {p.name for p in _evolution_modules()}
        assert SOLE_PROMOTER in names, names

    def test_no_module_but_core_promotion_calls_promote_or_rollback_to(self) -> None:
        offenders = []
        for path in _evolution_modules():
            if path.name == SOLE_PROMOTER:
                continue
            called = _called_method_names(path.read_text(encoding="utf-8"))
            hit = called & MUTATING_METHODS
            if hit:
                offenders.append((path.name, sorted(hit)))
        assert not offenders, f"unexpected Stable-mutating call: {offenders}"

    def test_core_promotion_calls_promote_and_never_rollback_to(self) -> None:
        source = (EVOLUTION_DIR / SOLE_PROMOTER).read_text(encoding="utf-8")
        called = _called_method_names(source)
        assert "promote" in called
        assert "rollback_to" not in called

    def test_no_evolution_module_performs_file_or_process_io_of_its_own(self) -> None:
        """This context orchestrates already-independent authorities; it
        opens no file and starts no process itself (mirrors
        `test_repair_pipeline_authority.py`'s identical control)."""
        for path in _evolution_modules():
            text = path.read_text(encoding="utf-8")
            for token in (
                "open(", "subprocess", "os.system", "os.replace", "os.remove",
                "shutil.", ".write_bytes(", ".write_text(",
            ):
                assert token not in text, f"{path.name}: {token}"


class TestNoShadowExecutionRouter:
    """D-026: the eight-tier execution-routing preference is composed from
    `engineering.factory.execution_routing.select_execution_tier`, never a
    second router. This context builds no AI-assisted candidate-generation
    step in Phase 23 (out of scope - see the Phase 23 package plan), so the
    property provable now is absence: no local tier-ordering vocabulary."""

    def test_no_evolution_module_declares_its_own_tier_ordering(self) -> None:
        watched = ("execution_tier", "deterministic_tool", "cloud_provider",
                   "human_governance", "local_model")
        offenders = [
            path.name for path in _evolution_modules()
            if any(term in path.read_text(encoding="utf-8").lower() for term in watched)
        ]
        assert not offenders, f"a local routing vocabulary was declared: {offenders}"
