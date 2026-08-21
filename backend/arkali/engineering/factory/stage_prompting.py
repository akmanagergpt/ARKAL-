"""Prompt construction for one staged-generation stage.

Owner: `engineering.factory`. Split out of `component_generation.py`
(ADR-0008 decomposition, not a GATE 8 exception): the module was already
at exactly its 400-logical-line ceiling before this session's manifests
dependency-convergence work (anti-loop retry logic, the `target_runtime`
signal below) pushed it over, measured by the real architecture-budget
gate, not assumed — the identical shape `manifest_context.py` was split
out for already. `_generate_one_stage`'s retry loop stays in
`component_generation.py`, since it also needs that module's own
`_StageEnvelope`/`_json_payload`/`_stage_findings`, and pulling those
across too would just move the circular-import problem rather than
solve it; this module owns only prompt construction, which has no such
dependency.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from arkali.control.specification.blueprint_contracts import RequirementBlueprint
from arkali.engineering.factory.generation_stages import StageDeclaration


def _stage_prompt(
    declaration: StageDeclaration, blueprint: RequirementBlueprint,
    visible_files: Mapping[str, str], prior_failure: str | None,
    target_runtime: str | None = None,
) -> str:
    payload: dict[str, object] = {
        "role": "You are one bounded stage of a multi-stage software factory.",
        "stage": declaration.name,
        "task": declaration.rule,
        "output_contract": {
            "format": "one JSON object only; no markdown or commentary",
            "schema": {"files": [{"path": "relative/posix/path", "content": "complete text"}]},
            "json_encoding_rule": (
                "Every file content is a JSON string. Escape newlines as \\n and "
                "all other control characters per RFC 8259."
            ),
        },
        "goal": blueprint.goal.goal_text,
        "requirements": [item.statement for item in blueprint.requirements],
        "visible_prior_files": visible_files,
        "prior_attempt_failure": prior_failure,
        "convergence_rule": (
            "When prior_attempt_failure is present, correct that exact defect "
            "while retaining everything else already correct."
        ),
    }
    if target_runtime is not None:
        # golden-work-047 (session evidence, frozen): the model was never
        # told what Python version its declared dependencies had to run
        # on. Mirrors `model_product_generation._prompt`'s existing
        # `target_runtime` field exactly; only the `manifests` stage
        # passes this today, since it is the only stage whose declared
        # rule (STAGED_GENERATION_STAGES.md) depends on it.
        payload["target_runtime"] = {"python": target_runtime}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
