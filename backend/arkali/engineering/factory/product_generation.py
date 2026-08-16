"""Deterministic real product generation from a resolved C-37 blueprint
(`ARK-REQ-0233`).

Owner: `engineering.factory`.

TIER 1 ONLY. This is the `deterministic_tool` tier's own generation work — the
same tier `execution_routing.py` names first in D-026's preference order.
No AI provider is contacted anywhere in this module, and none is claimed. Real
natural-language-driven generation is Probabilistic Edge territory this
capability does not reach; what is built here is a real, mechanical,
inspectable translation from a blueprint's own captured data into executable
Python, never invented business logic beyond what the blueprint itself states.

NO PLACEHOLDER STANDS IN FOR UNDERIVED LOGIC. Every generated function is
either a real derived check or an honest structured acknowledgement — a
bare unimplemented marker for logic that was never derived is refused by
this module's own design, matching MS Constitution 7's ban on treating an
unfinished stand-in as delivered implementation.

WHY THIS IS NOT GOLDEN FACTORY ACCEPTANCE. BP §Real program verification
during build separates two obligations: "generate progressively harder real
products through the normal pipeline" (this module, `ARK-REQ-0233`, Phase 16)
and "Golden Factory Acceptance requires at least one real provider or real
working local model" (`ARK-REQ-0234`/`0235`, Phase 30 — not claimed here, and
not claimable without a real provider this environment does not have).

WHAT "REAL" MEANS HERE, MEASURED, NOT ASSERTED. The generated module is
written into a real isolated `CandidateWorkspace` (C-25, Phase 12, reused not
copied), is genuinely importable Python, and every generated function is
either (a) a real, executable constraint check mechanically derived from a
requirement's own captured `acceptance_criteria` pattern, or (b) an honest
acknowledgement record for a requirement with no derivable check — never an
unimplemented-marker or static string standing in for logic that was
never derived (MS §Constitution 7). "Progressively harder" is a real,
measured property of the caller's own composed journey (more requirements,
more derived checks), not a claim this module makes about a single call.

REFUSAL, NOT SILENT INVENTION. `generate_product` raises
`UnresolvedBlueprintError` for any blueprint carrying an unresolved question —
Phase 16 never resolves what Phase 15 could not, and never generates from a
contradictory or ambiguous blueprint.

STRUCTURAL, NOT IMPORTED, COMPOSITION WITH THE WORKSPACE. `max_orchestration_depth`
was already 4 of 4 on `engineering.candidate`'s own existing chain into
`kernel.contracts`; a static import of `CandidateWorkspace` here would extend
it to 5. `WorkspaceTarget` below is a structural `Protocol` matching
`CandidateWorkspace.write`'s exact shape, so a real `CandidateWorkspace`
instance satisfies it and is genuinely reused at the call site — this module
just never adds the import edge that would lengthen the measured chain.
Decomposition per ADR-0008, not an exemption.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict, Field

from arkali.control.specification.blueprint_contracts import (
    CandidateRequirement,
    RequirementBlueprint,
)
from arkali.engineering.factory.errors import UnresolvedBlueprintError


class WorkspaceTarget(Protocol):
    """Structural match for `engineering.candidate.workspace.CandidateWorkspace.write`."""

    def write(self, relative: str, payload: bytes) -> pathlib.Path: ...

#: `at least|at most|no more than|no less than|within|exactly N unit` — the
#: same pattern `blueprint_engine.derive_acceptance_criteria` produces, read
#: back here to derive a real comparison, never re-parsed from prose.
_NUMERIC_CRITERION: Final[re.Pattern[str]] = re.compile(
    r"^(?P<op>at least|at most|no more than|no less than|within|exactly)\s+"
    r"(?P<value>[\d,]+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z%]*)$", re.I
)
_COMPARATORS: Final[dict[str, str]] = {
    "at least": ">=", "no less than": ">=",
    "at most": "<=", "no more than": "<=", "within": "<=",
    "exactly": "==",
}

GENERATED_MODULE_RELPATH: Final[str] = "generated_product/product.py"


class GeneratedFunction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    #: True when the function body is a real derived constraint check;
    #: False when it is an honest acknowledgement record (no check derivable).
    is_derived_check: bool


class GeneratedProduct(BaseModel):
    """What was actually written, and to where — carries no acceptance state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    blueprint_id: str
    module_relpath: str
    functions: tuple[GeneratedFunction, ...]

    @property
    def derived_check_count(self) -> int:
        return sum(1 for f in self.functions if f.is_derived_check)


def _slug(index: int, statement: str) -> str:
    words = [w for w in re.split(r"\W+", statement.lower()) if w][:6]
    return f"requirement_{index}_" + "_".join(words) if words else f"requirement_{index}"


def _render_check(name: str, criterion: str) -> str | None:
    match = _NUMERIC_CRITERION.match(criterion.strip())
    if match is None:
        return None
    comparator = _COMPARATORS[match.group("op").lower()]
    value = match.group("value").replace(",", "")
    return (
        f"def {name}(measured: float) -> bool:\n"
        f'    """Derived from acceptance criterion: {criterion!r}."""\n'
        f"    return measured {comparator} {value}\n"
    )


def _render_acknowledgement(name: str, requirement: CandidateRequirement) -> str:
    return (
        f"def {name}() -> dict[str, str]:\n"
        f'    """No mechanically derivable check exists for this requirement;\n'
        f'    honestly acknowledges it rather than inventing one."""\n'
        f"    return {{\n"
        f"        \"statement\": {requirement.statement!r},\n"
        f"        \"category\": {requirement.category.value!r},\n"
        f"    }}\n"
    )


def render_module(blueprint: RequirementBlueprint) -> tuple[str, tuple[GeneratedFunction, ...]]:
    """The generated source and its function manifest. Pure; writes nothing."""
    lines = [
        '"""Generated by ARKALI Phase 16 (C-37 -> deterministic_tool tier).',
        "",
        f"Source blueprint: {blueprint.blueprint_id}",
        f"Revision: {blueprint.revision}",
        '"""',
        "",
        "from __future__ import annotations",
        "",
    ]
    functions: list[GeneratedFunction] = []
    for requirement in blueprint.requirements:
        name = _slug(requirement.index, requirement.statement)
        rendered: str | None = None
        for criterion in requirement.acceptance_criteria:
            rendered = _render_check(name, criterion)
            if rendered is not None:
                break
        if rendered is not None:
            lines.append(rendered)
            functions.append(GeneratedFunction(name=name, is_derived_check=True))
        else:
            lines.append(_render_acknowledgement(name, requirement))
            functions.append(GeneratedFunction(name=name, is_derived_check=False))
        lines.append("")
    return "\n".join(lines), tuple(functions)


def generate_product(
    blueprint: RequirementBlueprint, workspace: WorkspaceTarget
) -> GeneratedProduct:
    """Write a real, importable module derived from `blueprint` into
    `workspace`. Refuses any blueprint carrying an unresolved question."""
    if not blueprint.is_fully_resolved:
        raise UnresolvedBlueprintError(
            f"blueprint {blueprint.blueprint_id} carries "
            f"{len(blueprint.unresolved)} unresolved question(s); "
            "Phase 16 does not resolve what Phase 15 could not"
        )
    source, functions = render_module(blueprint)
    workspace.write(GENERATED_MODULE_RELPATH, source.encode("utf-8"))
    return GeneratedProduct(
        blueprint_id=blueprint.blueprint_id,
        module_relpath=GENERATED_MODULE_RELPATH,
        functions=functions,
    )
