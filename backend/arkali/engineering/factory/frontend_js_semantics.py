"""One shared, regex-based semantic extraction layer for real JS/JSX source
this pipeline's own generated frontends produce.

Owner: `engineering.factory`. Before this module, `frontend_mutation_
contract.py` and `frontend_callback_arity_preflight.py` each independently
implemented near-identical regex logic to answer the same real question --
"what are this named function's own declared parameters" -- and did so
INCONSISTENTLY: `frontend_mutation_contract._function_params` recognized
`export const name = (...) =>`, `frontend_callback_arity_preflight._
function_definition_params` did not. Confirmed, reported, and consolidated
here rather than left as two silently-diverging copies.

NOT A FULL AST/TREE-SITTER PARSER. `ARCHITECTURE.md` §11 already specifies
one for real -- `engineering.codeintel`'s own frontend-contract graph,
built via a Tree-sitter adapter (ARK-REQ-0066, Phase 11) -- and
`codeintel.python_builder`'s own docstring is explicit that the adapter
does not exist yet ("`frontend-contract` requires TypeScript, which §11
assigns to a Tree-sitter adapter this build does not have"). Building that
real adapter is `engineering.codeintel`'s own, much larger undertaking (a
new dependency, a new graph node schema, rebuild-determinism evidence) --
out of this module's narrower, already-evidenced scope: replacing two
inconsistent regex copies with one consistent one, for the handful of real
JS shapes this pipeline's own generated frontends are evidenced to use.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

#: `(?:async\s+)?function name(...)` or `(?:export\s+)?(?:const|let|var)
#: name = (?:async\s*)?(...) =>` -- the two real function-declaration
#: shapes this pipeline's own generated `frontend_client`/component code
#: has ever used (golden-work-045/101/122, session evidence).
_FUNCTION_DEFINITION = re.compile(
    r"(?:async\s+)?function\s+(?P<fname1>\w+)\s*\(\s*(?P<params1>[^)]*)\)"
    r"|(?:export\s+)?(?:const|let|var)\s+(?P<fname2>\w+)\s*=\s*"
    r"(?:async\s*)?\(\s*(?P<params2>[^)]*)\)\s*=>"
)


def _function_parameters(name: str, source: str) -> tuple[str, ...] | None:
    """`name`'s own real declared parameter names, in order, from its one
    real definition anywhere in `source` -- `None` if `source` does not
    define it (a bare-reference prop almost always names an imported
    client function, defined in a different file than the one rendering
    the JSX), or if its parameter list is a destructured/array pattern
    (`({ id }) => ...`) rather than plain names: one real parameter, not
    several comma-separated ones, and too coarse to disambiguate safely
    without a real parser, so treated as unresolvable rather than risking
    a wrong count."""
    escaped = re.escape(name)
    match = re.search(
        rf"(?:async\s+)?function\s+{escaped}\s*\(([^)]*)\)"
        rf"|(?:export\s+)?(?:const|let|var)\s+{escaped}\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>",
        source,
    )
    if match is None:
        return None
    params_text = match.group(1) if match.group(1) is not None else match.group(2)
    if "{" in params_text or "[" in params_text:
        return None
    return tuple(p.strip() for p in params_text.split(",") if p.strip())


def _function_parameters_across_files(name: str, files: Mapping[str, str]) -> tuple[str, ...] | None:
    """`_function_parameters`, searched across every real file in `files`
    in a stable (insertion) order -- a bare-reference prop almost always
    names an imported client function, defined in a different file than
    the one rendering the JSX that references it."""
    for source in files.values():
        found = _function_parameters(name, source)
        if found is not None:
            return found
    return None


def _all_function_definitions(source: str) -> dict[str, tuple[str, ...]]:
    """Every real function `source` itself defines, name -> declared
    parameters -- skips a destructured/array-pattern definition (same
    posture as `_function_parameters`) rather than recording a wrong
    count for it."""
    found: dict[str, tuple[str, ...]] = {}
    for match in _FUNCTION_DEFINITION.finditer(source):
        fname = match.group("fname1") or match.group("fname2")
        params_text = match.group("params1") if match.group("fname1") else match.group("params2")
        if "{" in params_text or "[" in params_text:
            continue
        found[fname] = tuple(p.strip() for p in params_text.split(",") if p.strip())
    return found


__all__ = ["_all_function_definitions", "_function_parameters", "_function_parameters_across_files"]
