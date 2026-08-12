"""Phase 12 Package 4: stable mutation and canonical-stage boundaries."""

from __future__ import annotations

import copy
import pathlib
from typing import Any

import pytest
import yaml

from arkali.control.policy.agent_authority import AgentAuthority
from arkali.control.policy.policy_errors import (
    DirectStableMutationError,
    MalformedPolicyState,
)
from arkali.lifecycle.release.stable_path import (
    StableCandidatePath,
    StablePathError,
    StageReceipt,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
MAP = pathlib.Path("docs/canonical/AUTHORITY_MAP.yaml")


def mutation() -> dict[str, Any]:
    raw = yaml.safe_load((REPO / MAP).read_text(encoding="utf-8"))
    return copy.deepcopy(raw["stable_mutation"])


def write_map(root: pathlib.Path, value: dict[str, Any]) -> pathlib.Path:
    target = root / MAP
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump({"stable_mutation": value}), encoding="utf-8")
    return root


class TestDirectStableMutation:
    def test_every_declared_actor_and_an_unknown_actor_are_refused(self) -> None:
        authority = AgentAuthority.load(REPO)
        actors = (*authority.barred_actors(), "invented_escape_actor")
        assert actors
        for actor in actors:
            with pytest.raises(DirectStableMutationError):
                authority.assert_may_directly_mutate_stable(actor)

    def test_casing_and_padding_cannot_bypass_the_boundary(self) -> None:
        authority = AgentAuthority.load(REPO)
        actor = authority.barred_actors()[0]
        for presented in (actor.upper(), f"  {actor}  ", ""):
            with pytest.raises(DirectStableMutationError):
                authority.assert_may_directly_mutate_stable(presented)

    def test_permission_is_derived_and_conflicting_declarations_fail_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        value = mutation()
        permitted = "explicit_test_actor"
        value["direct_mutation_permitted_by"] = [permitted]
        authority = AgentAuthority.load(write_map(tmp_path / "permitted", value))
        authority.assert_may_directly_mutate_stable(permitted)

        value["direct_mutation_permitted_by"] = [value["prohibited_actors"][0]]
        with pytest.raises(MalformedPolicyState, match="both"):
            AgentAuthority.load(write_map(tmp_path / "conflict", value))


class TestCanonicalRequiredPath:
    def test_every_stage_is_derived_and_must_be_traversed_in_order(self) -> None:
        path = StableCandidatePath.load(REPO)
        declared = tuple(str(stage).lower() for stage in mutation()["required_path"])
        assert path.stages() == declared
        receipt = path.begin_candidate(candidate_id="candidate-1")
        assert receipt.stage == declared[1]
        for stage in declared[2:]:
            receipt = path.advance(receipt, to_stage=stage)
        assert receipt.stage == declared[-1]

    def test_skip_reverse_repeat_and_unknown_are_refused(self) -> None:
        path = StableCandidatePath.load(REPO)
        receipt = path.begin_candidate(candidate_id="candidate-1")
        for target in (path.stages()[-1], receipt.stage, path.stages()[0], "unknown"):
            with pytest.raises(StablePathError):
                path.advance(receipt, to_stage=target)

    def test_promotion_requires_the_immediately_preceding_stage(self) -> None:
        path = StableCandidatePath.load(REPO)
        receipt = path.begin_candidate(candidate_id="candidate-1")
        with pytest.raises(StablePathError):
            path.promotion_receipt(receipt)
        for stage in path.stages()[2:-1]:
            receipt = path.advance(receipt, to_stage=stage)
        promoted = path.promotion_receipt(receipt)
        assert promoted.stage == path.stages()[-1]
        assert promoted.candidate_id == receipt.candidate_id

    def test_a_fabricated_accepted_stage_without_the_prefix_is_refused(self) -> None:
        path = StableCandidatePath.load(REPO)
        fabricated = StageReceipt(
            candidate_id="candidate-1",
            stage=path.stages()[-2],
            traversed=(path.stages()[-2],),
        )
        with pytest.raises(StablePathError, match="complete canonical prefix"):
            path.promotion_receipt(fabricated)

    @pytest.mark.parametrize("declared", [[], ["only"], ["a", "a"]])
    def test_malformed_or_vacuous_paths_fail_closed(
        self, tmp_path: pathlib.Path, declared: list[str]
    ) -> None:
        value = mutation()
        value["required_path"] = declared
        with pytest.raises(StablePathError):
            StableCandidatePath.load(write_map(tmp_path, value))
