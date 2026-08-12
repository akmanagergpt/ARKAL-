"""C-22 harness task specification (ARK-REQ-0231, ARK-REQ-0054).

Owner: engineering.agent. Concern: `agent_task_bounding_and_context`.

THE PRIMITIVE IS A BOUNDED TASK, NOT A PROMPT. `MS §Harness Engineering` says so
in as many words: "The primitive is not 'send a prompt'; the primitive is
'execute a bounded engineering task'." This model is that primitive. A task that
cannot name its tools, its permissions, its workspace, its environment, what
counts as acceptance and how much repair it may spend is not a task this system
will execute.

BOUNDEDNESS IS STRUCTURAL, NOT POLICED. Every element is a REQUIRED field with
no default, and `extra="forbid"` means an undeclared attribute cannot be attached
at all. So a task missing an element cannot be constructed, rather than being
constructed and later audited — there is no window in which a half-specified
task exists. `ARK-REQ-0231` is therefore satisfied by the type, and
`reconcile_with_authority` proves the field set is still exactly what the
canonical documents declare rather than what someone typed here.

EMPTY IS A BOUND; ABSENT IS NOT. `tools=()` declares that the task may use no
tools, which is a real and useful boundary. Omitting `tools` declares nothing.
That distinction is the whole reason no field carries a default: pydantic would
otherwise collapse "explicitly none" and "never stated" into the same value, and
the second is exactly what `ARK-REQ-0231` forbids. Scalar elements additionally
refuse blank strings, because a blank acceptance target is not an acceptance
target.

WHAT THIS MODULE IS NOT THE AUTHORITY FOR. It does not own the element list —
`harness_elements.py` parses that from the canonical documents. It does not own
the permission vocabulary: `AUTHORITY_MAP.yaml` assigns operation classes to
`control.policy`, so permissions are carried as declared references and are
never validated against a private copy of that vocabulary here. Storing one
would be a shadow registry. It does not own the context package either; C-23 is
a separate contract and this task references it.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from arkali.engineering.agent.errors import (
    MalformedHarnessElement,
    UnboundedHarnessTask,
)
from arkali.engineering.agent.harness_elements import HarnessElementAuthority

C22_SOURCE = "MS §Harness Engineering + BP §Harness Engineering (C-22)"

#: A scalar element must say something. `min_length=1` after stripping is what
#: separates "declared" from "left blank and hoped nobody would look".
Declared = Annotated[str, Field(min_length=1)]


class HarnessTask(BaseModel):
    """One bounded engineering task, carrying every canonical harness element.

    The field set is reconciled against the canonical documents by
    `reconcile_with_authority`; it is not trusted because it looks right.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    #: What is to be done, bounded. Never a free-form instruction to "implement
    #: everything" - `BP §Harness Engineering` names that anti-pattern directly.
    task_specification: Declared
    #: The C-23 package identifier. This contract references it and does not
    #: embed it; provenance and no-secret enforcement belong to C-23.
    context_package: Declared
    #: Tool names the task may use. `()` declares none, which is a bound.
    tools: tuple[str, ...]
    #: Operation-class references, owned by `control.policy`. Carried, never
    #: re-derived or validated against a local vocabulary.
    permissions: tuple[str, ...]
    workspace: Declared
    environment: Declared
    #: What would make the output acceptable. An agent may not decide this for
    #: itself - `ARK-REQ-0051` is enforced in the policy path, not here.
    acceptance_target: Declared
    #: Bounded repair. Unbounded repair is not a budget, so this is a finite
    #: non-negative count and `control.repair` owns convergence.
    repair_budget: Annotated[int, Field(ge=0)]

    @classmethod
    def element_fields(cls) -> tuple[str, ...]:
        return tuple(cls.model_fields)

    @classmethod
    def reconcile_with_authority(cls, authority: HarnessElementAuthority) -> None:
        """Refuse unless this model carries exactly the canonical elements.

        Both directions. A canonical element with no field means a task could be
        constructed while unbounded in that dimension; a field with no canonical
        element means this contract invented a boundary the documents do not
        declare. Neither is survivable, so both raise.
        """
        declared = authority.field_names()
        carried = cls.element_fields()
        missing = tuple(name for name in declared if name not in carried)
        if missing:
            raise UnboundedHarnessTask(
                f"the canonical documents declare harness element(s) {list(missing)} "
                "that C-22 carries no field for; a task could be constructed "
                "unbounded in that dimension",
                source=C22_SOURCE,
            )
        extra = tuple(name for name in carried if name not in declared)
        if extra:
            raise MalformedHarnessElement(
                f"C-22 carries field(s) {list(extra)} that the canonical "
                "documents declare no harness element for",
                source=C22_SOURCE,
            )
        if carried != declared:
            raise MalformedHarnessElement(
                f"C-22 declares its elements in order {list(carried)}; the "
                f"canonical documents declare {list(declared)}",
                source=C22_SOURCE,
            )

    @property
    def is_bounded(self) -> bool:
        """Always True for a constructed task, and that is the point.

        Boundedness is enforced at construction by required fields and
        `extra="forbid"`, so an unbounded `HarnessTask` cannot exist to be asked.
        This property exists so a caller can state the invariant it is relying
        on, not so it can discover a task it should not have been given.
        """
        return True
