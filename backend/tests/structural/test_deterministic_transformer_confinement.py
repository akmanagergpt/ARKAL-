"""ARK-REQ-0240: deterministic transformers execute inside the candidate
lifecycle only, and the confinement is control.policy's, not
engineering.repair's own.

Phase 14 (post-Package-3, ARK-REQ-0240). Mirrors
`test_agent_role_separation.py::TestTheRoleDoesNotJudgeItsOwnProhibitions`
exactly, because ARK-REQ-0240 is the same shape of problem ARK-REQ-0051
already solved: an actor-boundary rule owned by control.policy, consumed —
never re-implemented — by the context it constrains.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any, Final

import pytest
import yaml

from arkali.control.policy.agent_authority import AgentAuthority
from arkali.control.policy.policy_errors import DirectStableMutationError
from arkali.engineering.repair.deterministic_transformer import (
    ACTOR,
    DeterministicTransformer,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
OWNER: Final[pathlib.Path] = REPO / "backend/arkali/engineering/repair"
AUTHORITY_MAP: Final[str] = "docs/canonical/AUTHORITY_MAP.yaml"


def stable_mutation_block() -> dict[str, Any]:
    raw: Any = yaml.safe_load((REPO / AUTHORITY_MAP).read_text(encoding="utf-8"))
    return dict(raw["stable_mutation"])


def owner_modules() -> list[pathlib.Path]:
    return sorted(p for p in OWNER.rglob("*.py") if p.name != "__init__.py")


def transformer(**overrides: object) -> DeterministicTransformer:
    values: dict[str, object] = {"name": "strip-trailing-whitespace", "version": "1.0.0"}
    values.update(overrides)
    return DeterministicTransformer.model_validate(values)


class TestTheActorLabelIsCanonicallyBarred:
    def test_the_live_authority_map_names_this_actor(self) -> None:
        """Derived, not assumed: the label this module presents to
        control.policy must actually be on the canonical barred list, or
        every check below would be exercising an actor nobody constrains."""
        block = stable_mutation_block()
        assert ACTOR in {str(a).strip().lower() for a in block["prohibited_actors"]}
        assert ACTOR not in {
            str(a).strip().lower() for a in block["direct_mutation_permitted_by"]
        }

    def test_the_live_authority_confirms_the_actor_is_barred(self) -> None:
        authority = AgentAuthority.load(REPO)
        assert authority.is_barred(ACTOR)


class TestTheModuleDoesNotJudgeItsOwnConfinement:
    def test_confinement_is_delegated_to_control_policy(self) -> None:
        """A transformer enforcing the rule that constrains it would be the
        actor grading its own paper. ARK-REQ-0240 is owned by control.policy."""
        source = (OWNER / "deterministic_transformer.py").read_text(encoding="utf-8")
        assert "AgentAuthority" in source
        code = source.split('"""')[-1]
        assert "prohibited_actors" not in code
        assert "direct_mutation_permitted_by" not in code
        assert "required_path" not in code

    def test_the_delegation_actually_refuses(self) -> None:
        """Delegation that never refuses would be decorative."""
        authority = AgentAuthority.load(REPO)
        with pytest.raises(DirectStableMutationError):
            transformer().assert_confined_to_candidate_lifecycle(authority)

    def test_the_refusal_names_the_actor_and_its_source(self) -> None:
        authority = AgentAuthority.load(REPO)
        with pytest.raises(DirectStableMutationError) as excinfo:
            transformer().assert_confined_to_candidate_lifecycle(authority)
        assert ACTOR in str(excinfo.value)


class TestEngineeringRepairAcquiredNoFurtherAuthority:
    """The requirement bars a direct Stable write; it does not, and must not,
    grant engineering.repair anything else — no release, promotion, Stable
    read/write, acceptance or lifecycle-transition capability."""

    FORBIDDEN_IMPORT_PREFIXES: Final[tuple[str, ...]] = (
        "arkali.lifecycle.",
        "arkali.acceptance.",
        "arkali.control.registry.",
    )

    def test_no_module_in_this_context_imports_a_forbidden_authority(self) -> None:
        offenders: list[str] = []
        for path in owner_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    name = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(self.FORBIDDEN_IMPORT_PREFIXES):
                            offenders.append(f"{path.name}: import {alias.name}")
                    continue
                else:
                    continue
                if name.startswith(self.FORBIDDEN_IMPORT_PREFIXES):
                    offenders.append(f"{path.name}: from {name} import ...")
        assert not offenders, f"forbidden authority imported: {offenders}"

    def test_no_module_defines_a_stable_write_promotion_or_rollback_operation(
        self,
    ) -> None:
        """A structural no-store, mirroring
        `test_agent_role_separation.py`'s provider-retention control: targets
        the real risk (this context becoming a second release/Stable
        authority) rather than the shape of any one identifier."""
        offenders: list[str] = []
        watched = ("promote", "rollback", "write_stable", "stable_write")
        for path in owner_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lowered = node.name.lower()
                    if any(term in lowered for term in watched):
                        offenders.append(f"{path.name}:{node.name}")
        assert not offenders, f"a release/Stable-authority operation is defined: {offenders}"

    def test_the_context_carries_no_second_copy_of_the_prohibited_actor_list(
        self,
    ) -> None:
        """F-0013: the governed list lives in AUTHORITY_MAP.yaml exactly once.

        Every OTHER canonical actor label is checked absent from this
        context's source (excluding this module's own docstring, which
        names them only to explain the derivation, never as code)."""
        others = {
            str(a).strip().lower()
            for a in stable_mutation_block()["prohibited_actors"]
            if str(a).strip().lower() != ACTOR
        }
        assert others, "no other prohibited actor to check against — test would be vacuous"
        offenders: list[str] = []
        for path in owner_modules():
            text = path.read_text(encoding="utf-8")
            code = text.split('"""')[-1] if path.name == "deterministic_transformer.py" else text
            for actor in others:
                if actor in code.lower():
                    offenders.append(f"{path.name}: {actor!r}")
        assert not offenders, f"a foreign actor label is hard-coded: {offenders}"


class TestDeterministicTransformerIsIdentityOnly:
    def test_it_carries_no_target_path_candidate_or_stable_reference(self) -> None:
        """BP §Deterministic repair names identity (narrow, idempotent,
        tested, versioned); it names no target. Adding one here would let
        this object decide what it may touch, which is exactly the judgement
        `control.policy` owns."""
        forbidden = ("path", "target", "candidate", "stable", "workspace")
        fields = set(DeterministicTransformer.model_fields)
        assert fields == {"name", "version"}
        for term in forbidden:
            assert not any(term in field for field in fields), term

    def test_it_is_immutable(self) -> None:
        from pydantic import ValidationError

        instance = transformer()
        with pytest.raises(ValidationError):
            instance.version = "2.0.0"  # type: ignore[misc]

    def test_an_undeclared_field_cannot_be_attached(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            transformer(target_path="src-tauri/")  # type: ignore[call-arg]
