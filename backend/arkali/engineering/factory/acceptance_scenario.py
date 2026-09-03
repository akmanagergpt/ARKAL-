"""A domain-independent contract for what a real Golden acceptance journey
must exercise, and where domain-specific facts to fill it come from.

Owner: `engineering.factory`. ARKALI's own production pipeline must generate
a dershane (Student/Fee) product today, and a completely different one --
inventory, task management, reservations, CRM -- tomorrow, unchanged. Before
this module, `run_golden_acceptance.py` and `run_golden_browser_journey.mjs`
hardcoded `/students`, `/payments`, `name`/`email`, `student_id`/`amount`/
`due_date` directly in the core runner: a real, confirmed architectural
leak of one specific Golden example into the pipeline that is meant to
prove ARKALI can generate ANY product, not validate this one forever.

`_AcceptanceScenario` carries every real domain fact the runner needs --
resources, their real routes, real create/update payloads, a real
relationship between two resources, navigation destinations, real editable
form fields, a real success indicator, whether a destructive action needs
confirmation -- so the runner itself never names a resource, a field, or a
route. A scenario is real data, not code: `golden/scenarios/
student_fee_management.json` is the Student/Fee Golden's own scenario, and
any other domain gets its own sibling file, never a change to this module
or the runner that consumes it.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _ResourceScenario(BaseModel):
    """One real resource (a REST collection) a scenario exercises."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Annotated[str, Field(min_length=1)]
    collection_route: Annotated[str, Field(min_length=1)]
    navigation_label: Annotated[str, Field(min_length=1)]
    #: The one-record form of `navigation_label` ("Student", not
    #: "Students") -- declared explicitly rather than guessed by
    #: singularization, the same real, evidenced ambiguity plural
    #: English spelling always carries.
    singular_label: Annotated[str, Field(min_length=1)]
    #: Real user-entered field names -- never a route-supplied identifier
    #: (the same exclusion `frontend_mutation_contract.py`'s own
    #: `form_fields` already applies on the generation side).
    editable_form_fields: tuple[str, ...] = Field(min_length=1)
    success_indicator_text: str = "success"
    destructive_confirmation_required: bool = False
    #: `{payload_key: resource_name}` -- a field in this resource's create
    #: payload that must be filled with an id created for a DIFFERENT,
    #: earlier resource in the same scenario (a real foreign-key
    #: relationship, e.g. a payment's own `student_id`).
    relationship_fields: dict[str, str] = Field(default_factory=dict)
    #: The real, reconciled MUTATION action set (`acceptance_plan_compiler.
    #: _resolved_actions`'s own already-computed result -- the subset of
    #: "create"/"edit"/"delete" BOTH the candidate's own `product_ux_spec.
    #: json` declares for this resource AND a real matching backend route/
    #: method actually backs; "view" is deliberately never a member -- it
    #: names no verb `_ACTION_TO_VERB` maps and a resource being rendered
    #: on a page at all already IS its own "view" observable, needing no
    #: separate coverage signal). This is the one real, domain-independent
    #: signal for "declared mandatory" a coverage check may use: an action
    #: present here is a real, backed promise the candidate made about
    #: itself, never something the runner or the browser journey invents
    #: or assumes.
    actions: tuple[str, ...] = ()


class _AcceptanceScenario(BaseModel):
    """One complete, domain-independent acceptance journey declaration.

    The runner (`run_golden_acceptance.py`) and the browser journey
    (`run_golden_browser_journey.mjs`, via this same JSON passed as a real
    file argument) both consume exactly this shape and name no resource,
    field, or route of their own.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: Annotated[str, Field(min_length=1)]
    resources: tuple[_ResourceScenario, ...] = Field(min_length=1)
    #: The resource the core create -> edit -> delete -> restart-
    #: persistence journey runs against.
    primary_resource: Annotated[str, Field(min_length=1)]
    create_payload: dict[str, object]
    update_payload: dict[str, object]
    #: A second resource created after the primary, real evidence of a
    #: relationship being honored (e.g. a payment referencing a student).
    #: `None` for a scenario with only one mutable resource.
    related_resource: str | None = None
    related_create_payload: dict[str, object] | None = None
    navigation_destinations: tuple[str, ...] = Field(min_length=1)
    #: Real, UI-distinguishable text values the browser journey types into
    #: the primary resource's own editable form fields -- deliberately
    #: separate from `create_payload`/`update_payload`: the API-created
    #: and the UI-created record exist in the SAME real running backend
    #: at once, and the browser journey must find its own row unambiguously
    #: (`getByText(browser_create_values[...])`), never one it did not
    #: itself create. `None` for a scenario the browser journey does not
    #: drive (backend-only fixture use).
    browser_create_values: dict[str, str] | None = None
    browser_update_values: dict[str, str] | None = None
    browser_related_values: dict[str, str] | None = None

    def resource(self, name: str) -> _ResourceScenario:
        for resource in self.resources:
            if resource.name == name:
                return resource
        raise KeyError(f"scenario {self.scenario_id!r} declares no resource named {name!r}")


__all__ = ["_AcceptanceScenario", "_ResourceScenario"]
