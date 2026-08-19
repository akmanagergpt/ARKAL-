"""ARK-REQ-0218 (BP §Mandatory): never use invented providers/metrics/
health/jobs for production acceptance (Phase 25).

This is proven structurally, not by convention: `runtime_telemetry.py`'s
`providers`/`agents`/`workers` dimensions can NEVER be constructed via
`DimensionReading.real` (the only constructor that carries `HonestState.
PASS` and a numeric value) anywhere in the shipping source, because no live
provider registry, agent runtime or worker pool exists on this host
(Phase 16/22's own acceptance records; DEF-009; Phase 8's own honestly-
recorded `CAPABILITY_NOT_CONFIGURED`). A future edit that fabricated one of
these three dimensions - hard-coding an invented "healthy" provider, say -
would fail this control, not merely a code-review opinion.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
RUNTIME_TELEMETRY = REPO / "backend" / "arkali" / "surfaces" / "operations" / "runtime_telemetry.py"

#: The three dimensions this repository has no live registry/runtime for.
_NO_LIVE_REGISTRY_DIMENSIONS = ("providers", "agents", "workers")


def _observe_runtime_return(tree: ast.Module) -> ast.Return:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "observe_runtime":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return):
                    return stmt
    raise AssertionError("observe_runtime no longer defines a return statement")


class TestProvidersAgentsWorkersCanNeverBeFabricated:
    def test_the_three_keyword_arguments_use_not_configured_never_real(self) -> None:
        tree = ast.parse(RUNTIME_TELEMETRY.read_text(encoding="utf-8"), filename=str(RUNTIME_TELEMETRY))
        return_stmt = _observe_runtime_return(tree)
        assert isinstance(return_stmt.value, ast.Call)
        by_keyword = {kw.arg: kw.value for kw in return_stmt.value.keywords}
        for dimension in _NO_LIVE_REGISTRY_DIMENSIONS:
            assert dimension in by_keyword, f"observe_runtime no longer sets {dimension!r}"
            value = by_keyword[dimension]
            assert isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
            assert value.func.attr == "not_configured", (
                f"{dimension} is constructed via {value.func.attr!r}, not "
                "not_configured -- this is exactly the fabrication ARK-REQ-0218 forbids"
            )

    def test_dimensionreading_real_never_appears_on_the_same_line_as_the_three_names(
        self,
    ) -> None:
        """A cheap, independent second proof: no source line in this module
        both names one of the three dimensions and calls `.real(`."""
        text = RUNTIME_TELEMETRY.read_text(encoding="utf-8")
        offenders = [
            line for line in text.splitlines()
            if ".real(" in line and any(f'"{d}"' in line for d in _NO_LIVE_REGISTRY_DIMENSIONS)
        ]
        assert not offenders, offenders


class TestTheNegativeControlWouldCatchARealFabrication:
    def test_a_fabricated_provider_reading_is_detected_by_the_same_assertion_shape(
        self,
    ) -> None:
        """NEGATIVE CONTROL: proves the AST check above is not vacuous."""
        fabricated = (
            "def observe_runtime(job_store, job_recovery, executor):\n"
            "    return RuntimeSnapshot(\n"
            "        providers=DimensionReading.real('providers', 3.0, 'fabricated'),\n"
            "    )\n"
        )
        tree = ast.parse(fabricated)
        return_stmt = _observe_runtime_return(tree)
        by_keyword = {kw.arg: kw.value for kw in return_stmt.value.keywords}
        value = by_keyword["providers"]
        assert isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
        assert value.func.attr == "real", "fixture itself is wrong: expected a .real() call"
