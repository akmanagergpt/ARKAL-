"""C-22: a harness task is bounded by construction (ARK-REQ-0231, ARK-REQ-0054).

Phase 10 Package 1. The claim under test is not "tasks are usually bounded" but
"an unbounded task cannot be constructed at all". So every control below tries to
build one and requires the attempt to fail, rather than building one and checking
a flag afterwards - a flag can be read late, or not at all.
"""

from __future__ import annotations

import pathlib
from typing import Any, Final

import pytest
from pydantic import ValidationError

from arkali.engineering.agent.errors import (
    MalformedHarnessElement,
    UnboundedHarnessTask,
)
from arkali.engineering.agent.harness_elements import HarnessElementAuthority
from arkali.engineering.agent.harness_task import HarnessTask

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def authority() -> HarnessElementAuthority:
    return HarnessElementAuthority.load(REPO)


def fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "task_specification": "add the /health route and its test",
        "context_package": "ctx-7f3a",
        "tools": ("read_file", "write_file"),
        "permissions": ("READ_FILE",),
        "workspace": "ws-ephemeral-12",
        "environment": "python-3.13.15",
        "acceptance_target": "tests/surfaces/test_health.py passes",
        "repair_budget": 3,
    }
    base.update(overrides)
    return base


class TestTheModelIsTheCanonicalElementSet:
    def test_it_reconciles_with_the_live_documents(
        self, authority: HarnessElementAuthority
    ) -> None:
        """The real contract against the real canonical set."""
        HarnessTask.reconcile_with_authority(authority)
        assert HarnessTask.element_fields() == authority.field_names()

    def test_a_canonical_element_with_no_field_is_refused(self) -> None:
        """A task could otherwise be constructed unbounded in that dimension."""
        extended = HarnessElementAuthority(
            HarnessElementAuthority.load(REPO).elements() + ("Escalation Path",),
            ("fixture",),
        )
        with pytest.raises(UnboundedHarnessTask, match="escalation_path"):
            HarnessTask.reconcile_with_authority(extended)

    def test_a_field_with_no_canonical_element_is_refused(self) -> None:
        """The contract may not invent a boundary the documents do not declare."""
        shortened = HarnessElementAuthority(
            HarnessElementAuthority.load(REPO).elements()[:-1], ("fixture",)
        )
        with pytest.raises(MalformedHarnessElement, match="repair_budget"):
            HarnessTask.reconcile_with_authority(shortened)

    def test_a_reordering_is_refused(self) -> None:
        """Order is part of the declaration."""
        live = HarnessElementAuthority.load(REPO).elements()
        swapped = HarnessElementAuthority((live[1], live[0]) + live[2:], ("fixture",))
        with pytest.raises(MalformedHarnessElement, match="order"):
            HarnessTask.reconcile_with_authority(swapped)


class TestAnUnboundedTaskCannotBeConstructed:
    def test_a_fully_bounded_task_is_accepted(self) -> None:
        task = HarnessTask(**fields())
        assert task.is_bounded
        assert task.repair_budget == 3

    @pytest.mark.parametrize("element", list(HarnessTask.element_fields()))
    def test_omitting_any_single_element_is_refused(self, element: str) -> None:
        """Every element, derived from the model rather than listed here."""
        incomplete = fields()
        del incomplete[element]
        with pytest.raises(ValidationError, match=element):
            HarnessTask(**incomplete)

    def test_an_undeclared_element_cannot_be_attached(self) -> None:
        with pytest.raises(ValidationError, match="escalation"):
            HarnessTask(**fields(escalation="ask a human"))

    @pytest.mark.parametrize(
        "element",
        ["task_specification", "context_package", "workspace", "environment",
         "acceptance_target"],
    )
    def test_a_blank_scalar_element_is_refused(self, element: str) -> None:
        """A blank acceptance target is not an acceptance target."""
        with pytest.raises(ValidationError):
            HarnessTask(**fields(**{element: "   "}))

    def test_a_negative_repair_budget_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            HarnessTask(**fields(repair_budget=-1))

    def test_a_task_is_immutable_once_bounded(self) -> None:
        """Bounds that can be widened after admission are not bounds."""
        task = HarnessTask(**fields())
        with pytest.raises(ValidationError):
            task.repair_budget = 99


class TestEmptyIsABoundAndAbsentIsNot:
    def test_declaring_no_tools_is_accepted(self) -> None:
        """`()` says the task may use no tools. That is a real boundary."""
        assert HarnessTask(**fields(tools=())).tools == ()

    def test_declaring_no_permissions_is_accepted(self) -> None:
        assert HarnessTask(**fields(permissions=())).permissions == ()

    def test_omitting_tools_entirely_is_still_refused(self) -> None:
        """The distinction the whole no-default design exists to preserve."""
        incomplete = fields()
        del incomplete["tools"]
        with pytest.raises(ValidationError, match="tools"):
            HarnessTask(**incomplete)

    def test_zero_repair_budget_is_a_budget(self) -> None:
        """Zero repairs is bounded. It is not the same as unbounded."""
        assert HarnessTask(**fields(repair_budget=0)).repair_budget == 0


class TestThisContractStoresNoOtherAuthoritysVocabulary:
    def test_permissions_are_carried_as_references_not_validated_locally(self) -> None:
        """`control.policy` owns operation classes; a local copy would shadow it.

        The task accepts an identifier this context cannot judge, precisely
        because judging it here would make `engineering.agent` a second
        permission authority.
        """
        task = HarnessTask(**fields(permissions=("SOME_UNKNOWN_CLASS",)))
        assert task.permissions == ("SOME_UNKNOWN_CLASS",)

    def test_no_module_of_this_context_declares_an_operation_class_list(self) -> None:
        owner = REPO / "backend/arkali/engineering/agent"
        governed = {"READ_FILE", "WRITE_FILE", "WRITE_STABLE_FILE", "ROLLBACK_STABLE"}
        offenders: list[str] = []
        for path in sorted(owner.rglob("*.py")):
            body = "\n".join(
                line for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            )
            offenders.extend(f"{path.name}: {name}" for name in governed if name in body)
        assert not offenders, f"policy vocabulary copied here: {offenders}"
