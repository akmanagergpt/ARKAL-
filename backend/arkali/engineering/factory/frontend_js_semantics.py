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

`_component_destructured_props` and `_balanced_brace_body` are the same
consolidation, one seam later: `frontend_manifest_preflight._route_
component_missing_props_findings` and `frontend_callback_arity_preflight`
each independently needed "a named component's own destructured prop
names" / "the real body text following a brace" and each grew its own
private copy first. Promoted here, unchanged in behavior, when
`frontend_form_initial_state_preflight.py` needed both at once rather than
writing a third copy of either.

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


#: `function Name({ a, b })` or `const Name = ({ a, b }) =>` -- a component
#: definition whose one real parameter is a destructured props object, the
#: idiomatic shape every real evidenced generated component this pipeline
#: has produced uses (`StudentForm`, `StudentEdit`, ...). Captures only the
#: destructure block's own text; `_destructured_names` below splits it.
_COMPONENT_DESTRUCTURED_PROPS_PATTERN = r"(?:const|function)\s+{name}\s*=?\s*\(\s*\{{\s*([^}}]*)\}}"


def _destructured_names(props_block: str) -> set[str]:
    """`{ a, b: renamed, c = 1 }` -> `{"a", "b", "c"}` -- the real local
    prop NAME being bound, stripped of any rename (`:`) or default
    value (`=`)."""
    return {
        part.strip().split(":")[0].split("=")[0].strip()
        for part in props_block.split(",") if part.strip()
    }


def _component_destructured_props(name: str, source: str) -> set[str] | None:
    """`name`'s own real destructured prop names, from its one real
    definition anywhere in `source` -- `None` if `source` never defines
    `name` this way (a class component, a non-destructured single prop,
    or simply not present), never guessed."""
    match = re.search(
        _COMPONENT_DESTRUCTURED_PROPS_PATTERN.format(name=re.escape(name)), source,
    )
    if match is None:
        return None
    return _destructured_names(match.group(1))


def _balanced_brace_body(text: str, open_brace_index: int) -> str:
    """The real text strictly between the `{` at `open_brace_index` and its
    own matching `}`, tracking nesting depth -- never a naive `[^}]*`
    match, which stops at the first inner closing brace a nested object
    or block already contains."""
    depth = 0
    for index in range(open_brace_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_index + 1:index]
    return text[open_brace_index + 1:]


__all__ = [
    "_all_function_definitions", "_balanced_brace_body", "_component_destructured_props",
    "_function_parameters", "_function_parameters_across_files",
]
