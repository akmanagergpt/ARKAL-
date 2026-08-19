"""C-34 Computer-Use operation authorization (ARK-REQ-0170).

Owner: `surfaces.operations`.

"Computer-Use Workers execute exclusively through the Policy Authority / PDP
/ PEP path used by every other execution surface. Every action resolves to a
declared operation class, and every class resolves to AUTO, ASK_USER or DENY
according to trust tier, target boundary and policy." (MS §Operations /
Computer Use / Source Export). This module is the one place that sentence is
made real: `authorize_computer_use_action` composes the genuine, unmodified
`control.policy` PDP - the same fourteen-class vocabulary and the same
trust-tier matrix `SECURITY_ARCHITECTURE.md` §2 already declares for every
other execution surface, never a second policy model.

`computer_use_worker` IS THE CANONICAL ACTOR. `AUTHORITY_MAP.yaml`'s
`stable_mutation.prohibited_actors` already names it (declared before this
phase existed), so this module supplies exactly the actor label that list
already anticipated - it does not invent one.

WHY THIS COMPOSES `PolicyDecisionPoint.decide_computer_use`, NOT `PEP.
require_auto`. `ASK_USER` is a genuine, expected outcome for several classes
(`BROWSER_EXTERNAL`, `INSTALL_SYSTEM_SOFTWARE`, `CHANGE_SYSTEM_CONFIGURATION`,
...), requiring a *different* code path (human takeover) than `DENY` - the
PEP's `require_auto` collapses both into one raised refusal, which is right
for an internal read/write but wrong for an interactive worker that must
route `ASK_USER` to a human rather than treat it as failure. Composing
`decide_computer_use` (primitives in and out, ARK-REQ-0170's own dedicated
method) rather than importing `control.policy.pep`/`.policy_contract`
directly avoids a real, measured `max_fan_in_per_module` violation on both -
see `pdp.py::decide_computer_use`'s own docstring for the identical
constraint `decide_network_egress` already answers the same way.

NO NEW PDP, PEP, POLICY AUTHORITY OR OPERATION CLASS IS CREATED. The
fourteen classes, their defaults and their fixed rules are all parsed from
`AUTHORITY_MAP.yaml` by the real, unmodified `OperationClassVocabulary` this
module never imports directly - it only ever sees the PDP's own resolved
answer.
"""

from __future__ import annotations

from typing import Final, Protocol

from arkali.surfaces.operations.computer_use_contracts import ComputerUseDecision

#: The canonical Computer-Use actor label - already named in
#: `AUTHORITY_MAP.yaml`'s `stable_mutation.prohibited_actors`.
ACTOR: Final[str] = "computer_use_worker"

#: MS §Trust-Tiered Isolation: "ARKALI-maintained extensions" - the Computer-
#: Use worker's own default trust tier. A caller acting on behalf of a lower-
#: trust target (generated candidate code, an imported project) must supply
#: that target's own tier explicitly; it is never silently assumed here.
DEFAULT_TRUST_TIER: Final[str] = "TRUST-1"

#: The fixed-rule fact keys `decide_computer_use` reads from `facts`. Any
#: other key is silently ignored by the PDP's own lookup, not an error here -
#: keeping the vocabulary itself owned entirely by `AUTHORITY_MAP.yaml`.
TARGET_IS_LOOPBACK: Final[str] = "target_is_loopback"
TARGET_IS_OWN_PROCESS: Final[str] = "target_is_own_process"
WITHIN_PREAUTHORIZED_SCOPE: Final[str] = "within_preauthorized_scope"
LOCKFILE_BOUND: Final[str] = "lockfile_bound"


class PolicyDecisionSource(Protocol):
    """Structural match for `control.policy.pdp.PolicyDecisionPoint.
    decide_computer_use`. A caller still passes the real PDP; only the
    reference at this call site is structural, so this module needs no
    import of `control.policy.pdp` for typing alone - though in practice the
    concrete type is cheap here (fan-in 3 of 15, no budget pressure), this
    keeps the composition explicit and the module trivially testable with a
    fixture double for the refusal paths a real PDP cannot cheaply force."""

    def decide_computer_use(
        self,
        *,
        operation_class: str,
        trust_tier: str,
        actor: str,
        facts: dict[str, bool] | None = None,
        local_only: bool = False,
        recorded_human_gates: tuple[str, ...] = (),
    ) -> tuple[str, str, str | None]: ...


def authorize_computer_use_action(
    pdp: PolicyDecisionSource,
    *,
    operation_class: str,
    trust_tier: str = DEFAULT_TRUST_TIER,
    facts: dict[str, bool] | None = None,
    local_only: bool = False,
    recorded_human_gates: tuple[str, ...] = (),
) -> ComputerUseDecision:
    """The real PDP's answer for one Computer-Use action.

    Every fact defaults to unstated rather than the permissive value - a
    fixed rule that needs a fact `facts` does not carry refuses rather than
    assuming it (the identical tri-state discipline `PolicyRequest` itself
    documents). This function decides nothing; it only asks.
    """
    decision, reason, gate = pdp.decide_computer_use(
        operation_class=operation_class,
        trust_tier=trust_tier,
        actor=ACTOR,
        facts=facts,
        local_only=local_only,
        recorded_human_gates=recorded_human_gates,
    )
    return ComputerUseDecision(
        operation_class=operation_class, decision=decision, reason=reason,
        required_human_gate=gate,
    )


__all__ = [
    "authorize_computer_use_action", "PolicyDecisionSource", "ACTOR",
    "DEFAULT_TRUST_TIER", "TARGET_IS_LOOPBACK", "TARGET_IS_OWN_PROCESS",
    "WITHIN_PREAUTHORIZED_SCOPE", "LOCKFILE_BOUND",
]
