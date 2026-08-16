"""D-026 composition, not a second authority (ARK-REQ-0392, ARK-REQ-0393).

`execution_routing.py` must import no durable-job authority (so it cannot
touch durable state), define no worker/provider/capability data of its own,
and hold no literal bounded-context owner name outside its own docstring
rationale (the tier order and NOT_CONFIGURED reasoning are the only fixed
data; every live answer is supplied by the caller).
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
ROUTING: Final[pathlib.Path] = (
    REPO / "backend/arkali/engineering/factory/execution_routing.py"
)

#: No durable-job authority may be imported; this module touches no job state.
FORBIDDEN_IMPORT_PREFIXES: Final[tuple[str, ...]] = (
    "arkali.execution.durable.",
    "arkali.execution.workflow.",
    "arkali.control.registry.provider.",
    "arkali.acceptance.",
    "arkali.lifecycle.",
)


def _tree() -> ast.AST:
    return ast.parse(ROUTING.read_text(encoding="utf-8"), filename=str(ROUTING))


class TestNoDurableOrProviderAuthorityIsImported:
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


class TestNoDurableOrProviderStateIsTouched:
    def test_the_module_performs_no_filesystem_or_process_io(self) -> None:
        text = ROUTING.read_text(encoding="utf-8")
        for token in ("open(", "subprocess", "os.system", "shutil.",
                      ".write_bytes", ".write_text"):
            assert token not in text, token

    def test_the_module_defines_no_job_mutation_or_provider_registration_operation(
        self,
    ) -> None:
        watched = ("write_job", "mutate_job", "register_provider", "create_provider",
                   "cache_provider", "store_provider")
        offenders = [
            node.name
            for node in ast.walk(_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(term in node.name.lower() for term in watched)
        ]
        assert not offenders, f"a job/provider mutation operation is defined: {offenders}"


class TestNoResultShapeCanBeMisreadAsSuccess:
    def test_no_pass_fail_or_bool_success_field_exists_on_tier_selection(self) -> None:
        text = ROUTING.read_text(encoding="utf-8")
        assert "class TierSelection" in text
        section = text.split("class TierSelection")[1].split("\nclass ")[0]
        for token in ("success: bool", "passed: bool", "ok: bool", "PASS = "):
            assert token not in section, token
