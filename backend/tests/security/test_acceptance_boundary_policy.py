"""Phase 13 Package 4: policy-owned acceptance actor prohibitions."""

from __future__ import annotations

import pathlib
from typing import Any, Final

import pytest
import yaml
from arkali.control.policy.acceptance_boundary import AcceptanceBoundaryPolicy
from arkali.control.policy.policy_errors import (
    CanonicalRequirementMutation,
    HumanGateNotRecorded,
    ProtectedCoreMutation,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
MAP = "docs/canonical/AUTHORITY_MAP.yaml"


@pytest.fixture(scope="module")
def policy() -> AcceptanceBoundaryPolicy:
    return AcceptanceBoundaryPolicy.load(REPO)


def canonical() -> dict[str, Any]:
    return yaml.safe_load((REPO / MAP).read_text(encoding="utf-8"))


def write_map(root: pathlib.Path, raw: dict[str, Any]) -> pathlib.Path:
    target = root / MAP
    target.parent.mkdir(parents=True)
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return root


def waiver_gate() -> str:
    matches = [
        gate for gate, text in canonical()["human_gates"].items()
        if "applicability waiver" in text.lower()
    ]
    assert len(matches) == 1
    return matches[0]


class TestAuthorityIsDerived:
    def test_actor_and_gate_vocabularies_match_authority(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        raw = canonical()
        assert set(policy.automated_actors()) == set(raw["stable_mutation"]["prohibited_actors"])
        assert set(policy.human_gates()) == set(raw["human_gates"])

    def test_a_new_automated_actor_is_immediately_constrained(
        self, tmp_path: pathlib.Path
    ) -> None:
        raw = canonical()
        raw["stable_mutation"]["prohibited_actors"].append("new_implementer")
        changed = AcceptanceBoundaryPolicy.load(write_map(tmp_path, raw))
        with pytest.raises(CanonicalRequirementMutation):
            changed.assert_may_author_applicability("new_implementer")

    @pytest.mark.parametrize("damage", ["actors", "gates", "waiver"])
    def test_missing_or_ambiguous_authority_fails_closed(
        self, tmp_path: pathlib.Path, damage: str
    ) -> None:
        raw = canonical()
        if damage == "actors":
            raw["stable_mutation"]["prohibited_actors"] = []
        elif damage == "gates":
            raw["human_gates"] = {}
        else:
            raw["human_gates"]["HUMAN_GATE_X"] = "another applicability waiver"
        with pytest.raises(Exception, match="actor|gate|waiver"):
            AcceptanceBoundaryPolicy.load(write_map(tmp_path / damage, raw))


class TestApplicabilityBoundary:
    def test_every_automated_actor_is_barred_from_authorship_and_classification(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        for actor in policy.automated_actors():
            with pytest.raises(CanonicalRequirementMutation):
                policy.assert_may_author_applicability(actor)
            with pytest.raises(CanonicalRequirementMutation):
                policy.assert_may_originate_not_applicable(actor)

    def test_evaluation_is_not_prohibited(self, policy: AcceptanceBoundaryPolicy) -> None:
        assert not hasattr(policy, "assert_may_evaluate_applicability")

    def test_non_automated_authority_is_not_misclassified(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        policy.assert_may_author_applicability("human_acceptance_authority")


class TestWaiverAndAcceptanceBoundary:
    def test_mandatory_cannot_be_waived_by_any_automated_actor(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        for actor in policy.automated_actors():
            with pytest.raises(CanonicalRequirementMutation):
                policy.assert_may_waive(
                    actor=actor,
                    mandatory=True,
                    recorded_human_gates=(waiver_gate(),),
                )

    def test_automated_actor_cannot_use_the_human_gate_as_a_waiver_token(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        for actor in policy.automated_actors():
            with pytest.raises(CanonicalRequirementMutation):
                policy.assert_may_waive(
                    actor=actor,
                    mandatory=False,
                    recorded_human_gates=(waiver_gate(),),
                )

    def test_exceptional_waiver_requires_derived_human_gate(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        with pytest.raises(HumanGateNotRecorded, match=waiver_gate()):
            policy.assert_may_waive(actor="human", mandatory=False)
        policy.assert_may_waive(
            actor="human",
            mandatory=False,
            recorded_human_gates=(waiver_gate(),),
        )

    def test_every_automated_actor_is_barred_from_weakening(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        for actor in policy.automated_actors():
            with pytest.raises(ProtectedCoreMutation):
                policy.assert_may_weaken_acceptance(actor)

    def test_machine_verdict_never_substitutes_for_any_human_gate(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        for gate in policy.human_gates():
            with pytest.raises(HumanGateNotRecorded, match=gate):
                policy.assert_machine_gate_boundary(
                    required_gate=gate, recorded_human_gates=()
                )
            policy.assert_machine_gate_boundary(
                required_gate=gate, recorded_human_gates=(gate,)
            )

    def test_no_required_gate_is_a_valid_machine_only_case(
        self, policy: AcceptanceBoundaryPolicy
    ) -> None:
        policy.assert_machine_gate_boundary(
            required_gate=None, recorded_human_gates=()
        )

    def test_unknown_gate_fails_closed(self, policy: AcceptanceBoundaryPolicy) -> None:
        with pytest.raises(HumanGateNotRecorded, match="unknown"):
            policy.assert_machine_gate_boundary(
                required_gate="HUMAN_GATE_UNKNOWN", recorded_human_gates=()
            )


class TestNoShadowAuthorityOrVerdict:
    def test_shipping_module_copies_no_actor_or_gate_identifier(self) -> None:
        source = (
            REPO / "backend/arkali/control/policy/acceptance_boundary.py"
        ).read_text(encoding="utf-8")
        code = source.split('"""')[-1]
        raw = canonical()
        for label in (
            *raw["stable_mutation"]["prohibited_actors"],
            *raw["human_gates"],
        ):
            assert repr(label) not in code and f'"{label}"' not in code

    def test_package_issues_no_verdict(self, policy: AcceptanceBoundaryPolicy) -> None:
        assert not any("verdict" in name for name in vars(type(policy)))
