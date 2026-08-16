"""HUMAN APPROVAL as an enforced policy stop (ARK-REQ-0330).

Owner: `control.policy` (Protected Core).

WHY THIS IS OWNED BY `control.policy`, NOT `execution.workflow`. The canonical
`WorkflowExecution` state machine (Phase 3, `execution.workflow`) already
structurally requires `context["human_approval_recorded"]` to release
`WAITING_APPROVAL` - but *what value that fact is allowed to take* is a policy
question, not a workflow one: `EXECUTION_AND_CAPABILITY.md` §5 states "HUMAN
APPROVAL is an enforced policy stop resolved by the PDP, not a visual
element", and `ARCHITECTURE.md` §6 names the Workflow Execution lifecycle's
human gate as "GATE per HUMAN APPROVAL node". A boolean an executor could set
from any caller-supplied context is not an enforcement; this module is what
makes it one, the same way `AcceptanceBoundaryPolicy` is what makes
`stable_mutation.prohibited_actors` an enforcement rather than a list.

NO SECOND AUTOMATED-ACTOR LIST. `automated_actors()` is parsed from
`AUTHORITY_MAP.yaml` `stable_mutation.prohibited_actors` on every load, the
exact same source and the exact same idiom `AcceptanceBoundaryPolicy` already
uses - not a private copy. That list already names `workflow` (MS §Constitution
6): a workflow execution path attempting to record its own approval is
refused by the same governed data an audit already recognises, not by a new
rule invented for this module.

STALENESS IS A POLICY QUESTION TOO. `is_enforced_approval` refuses an
approval recorded against a graph revision that is no longer current - an
approval granted for one canonical revision must not silently authorise
execution of a different one a later edit produced. This is the HUMAN
APPROVAL analogue of ADR-0004's "a stale-hash derived representation is never
executed", applied to a policy decision rather than a compiled plan.

THIS MODULE RECORDS NOTHING. Persisting a decision is `execution.workflow`'s
concern (its own persisted, execution-scoped record); this module only
answers two questions about facts a caller supplies: may this actor attempt
to record one, and does a given recorded decision actually authorise
advancing past `WAITING_APPROVAL`.
"""

from __future__ import annotations

import pathlib

from arkali.control.policy.authority_source import (
    load_authority_map,
    refuse,
    require_section,
)
from arkali.control.policy.policy_errors import AutomatedActorCannotApprove

#: The only decision value that ever authorises advancing past
#: `WAITING_APPROVAL`. A rejection, or any other value, never does.
APPROVED = "APPROVED"


class WorkflowApprovalGate:
    """The enforced HUMAN APPROVAL policy stop. Construct with `load`."""

    def __init__(self, automated_actors: frozenset[str], source: str) -> None:
        self._automated = automated_actors
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> WorkflowApprovalGate:
        raw, source = load_authority_map(repo_root)
        mutation = require_section(raw, "stable_mutation", source)
        if not isinstance(mutation, dict):
            raise refuse("stable_mutation must be a mapping", source)
        actors = frozenset(
            str(item).strip().lower()
            for item in (mutation.get("prohibited_actors") or [])
            if str(item).strip()
        )
        if not actors:
            raise refuse("no automated/prohibited actors are declared", source)
        return cls(actors, source)

    def automated_actors(self) -> tuple[str, ...]:
        return tuple(sorted(self._automated))

    def assert_may_record(self, actor: str) -> None:
        """Refuse an automated actor attempting to record an approval.

        `workflow` is already a declared prohibited actor - a workflow
        execution path (including the executor itself) may never supply its
        own approval. Only an actor label outside the governed automated set
        may record one; the PEP call site that invokes this is what actually
        proves the caller *is* what it claims.
        """
        normalised = actor.strip().lower()
        if normalised in self._automated:
            raise AutomatedActorCannotApprove(
                f"{actor!r} may not record a HUMAN APPROVAL decision; it is a "
                "declared automated actor under stable_mutation.prohibited_actors",
                source=self.source,
            )

    def is_enforced_approval(
        self,
        *,
        decision: str,
        actor: str,
        approval_revision_hash: str,
        current_revision_hash: str,
    ) -> bool:
        """Whether a recorded decision actually authorises advancing past
        `WAITING_APPROVAL`.

        Every condition narrows toward refusal, never toward permission: an
        automated actor never authorises (even if somehow recorded), a
        rejection never authorises, and an approval bound to a revision that
        is no longer current never authorises - the same "never widens"
        discipline the PDP itself follows.
        """
        if actor.strip().lower() in self._automated:
            return False
        if decision != APPROVED:
            return False
        return approval_revision_hash == current_revision_hash
