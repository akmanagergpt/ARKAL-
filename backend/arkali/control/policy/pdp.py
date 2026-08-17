"""The Policy Decision Point (ARK-REQ-0097, 0104, 0107, 0171-0175).

Owner: control.policy (Protected Core).

THERE IS EXACTLY ONE PDP. No component computes its own decision or caches one
(SECURITY_ARCHITECTURE.md §1). It is pure and deterministic: same facts, same
decision, no clock, no randomness, no network, no AI.

FAIL CLOSED. A decision that cannot be resolved is DENY, and an unresolvable
*input* raises rather than resolving to anything. The order of evaluation is
deliberate and is the security property itself:

  1. the operation must map to a canonical class          -> else DENY
  2. an absolute fixed rule wins over everything           -> DENY / gated
  3. Local-Only wins over the tier matrix                  -> DENY
  4. the tier matrix supplies the base decision
  5. remaining fixed rules may only *narrow* that decision
  6. unsatisfiable isolation narrows an executing op to DENY

A later step may never widen an earlier one. There is no branch in this module
that turns a DENY or ASK_USER into AUTO.
"""

from __future__ import annotations

import pathlib

from pydantic import BaseModel, ConfigDict

from arkali.control.policy.authority_source import load_authority_map, refuse
from arkali.control.policy.operation_class import (
    Decision,
    OperationClassRule,
    OperationClassVocabulary,
)
from arkali.control.policy.policy_contract import PolicyDecisionRecord, PolicyRequest
from arkali.control.policy.policy_errors import MalformedPolicyState
from arkali.control.policy.security_matrix import SecurityMatrix

_SOURCE = "AUTHORITY_MAP.yaml + SECURITY_ARCHITECTURE.md §1-§2"


class PolicyAuthority(BaseModel):
    """Governed policy facts the PDP needs, parsed - never declared here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rollback_invoker: str
    human_gates: tuple[str, ...]
    stable_direct_mutation_permitted_by: tuple[str, ...]
    source_path: str

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> PolicyAuthority:
        raw, source = load_authority_map(repo_root)
        mutation = raw.get("stable_mutation") or {}
        exception = mutation.get("sole_exception") or {}
        invoker = exception.get("invoker")
        if not invoker:
            raise refuse(
                "stable_mutation.sole_exception.invoker is not declared", source
            )
        return cls(
            rollback_invoker=str(invoker),
            human_gates=tuple(sorted(raw.get("human_gates", {}))),
            stable_direct_mutation_permitted_by=tuple(
                mutation.get("direct_mutation_permitted_by") or ()
            ),
            source_path=source,
        )


def _narrow(current: Decision, proposed: Decision) -> Decision:
    """Return the stricter of two decisions. Never widens."""
    order = {Decision.AUTO: 0, Decision.ASK_USER: 1, Decision.DENY: 2}
    return current if order[current] >= order[proposed] else proposed


class PolicyDecisionPoint:
    """The single deterministic decision point."""

    def __init__(
        self,
        vocabulary: OperationClassVocabulary,
        matrix: SecurityMatrix,
        authority: PolicyAuthority,
    ) -> None:
        self.vocabulary = vocabulary
        self.matrix = matrix
        self.authority = authority

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> PolicyDecisionPoint:
        return cls(
            OperationClassVocabulary.load(repo_root),
            SecurityMatrix.load(repo_root),
            PolicyAuthority.load(repo_root),
        )

    def decide(self, request: PolicyRequest) -> PolicyDecisionRecord:
        """Resolve one request. Raises only on malformed or unmappable input."""
        rule = self.vocabulary.get(request.operation_class)
        self._require_known_tier(request)

        absolute = self._absolute_rule(rule, request)
        if absolute is not None:
            return absolute

        decision, why = self._base_decision(rule, request)
        decision, why = self._apply_narrowing(decision, why, rule, request)
        gate = self._required_gate(rule, request)
        if gate is not None and gate not in request.recorded_human_gates:
            decision = _narrow(decision, Decision.ASK_USER)
            why = f"{why}; requires {gate}, not recorded"
        return self._record(request, decision, rule.name, why, gate)

    def decide_or_deny_unmapped(self, request: PolicyRequest) -> PolicyDecisionRecord:
        """Like `decide`, but an unmappable `operation_class` resolves to a
        recorded decision instead of raising (ARK-REQ-0166).

        `SECURITY_ARCHITECTURE.md` §2: "Any action not mappable to a class
        is DENY." `decide` deliberately raises for this case - this module's
        own docstring: "an unresolvable *input* raises rather than resolving
        to anything" - which suits a caller that can treat an exception as
        the refusal. A caller that cannot afford to (a plugin action
        invocation, where an uncaught exception would itself be the "crashes
        core" failure ARK-REQ-0164 forbids) needs the refusal recorded and
        audited like any other decision. `decide`'s own raising behaviour is
        unchanged by this method; this is a second, additive entry point,
        never a replacement, and the resolution is read from
        `AUTHORITY_MAP.yaml`'s `unmapped_action_resolution`, never
        hard-coded here.
        """
        if not self.vocabulary.contains(request.operation_class):
            self._require_known_tier(request)
            return self._record(
                request, self.vocabulary.unmapped_resolution, request.operation_class,
                "operation class maps to no canonical class; resolution taken "
                "from AUTHORITY_MAP.yaml unmapped_action_resolution", None,
            )
        return self.decide(request)

    def decide_network_egress(
        self,
        *,
        actor: str,
        trust_tier: str,
        local_only: bool,
        target_is_loopback: bool | None = None,
    ) -> str:
        """`NETWORK_EXTERNAL`'s decision, as a plain string, for a caller
        that cannot import `policy_contract.PolicyRequest` (fan-in ceiling
        15 of 15 - see `decide_or_deny_unmapped`'s docstring for the sibling
        constraint this method answers the same way: primitive facts in,
        the `Decision` value out as `str`, so a structural `Protocol`
        mirroring this exact signature needs no import of this module's own
        types either).

        `engineering.plugin`'s Research capability (ARK-REQ-0163) is this
        method's first caller: MS's Local-Only rule marks `NETWORK_EXTERNAL`
        `DENY in Local-Only` (`SECURITY_ARCHITECTURE.md` §2), and the
        Verification and Delivery Contract names "research" as one of the
        paths whose Local-Only DENY must be evidenced - this reuses the real
        PDP rather than asserting the rule a second time.
        """
        return self.decide(
            PolicyRequest(
                operation_class="NETWORK_EXTERNAL",
                trust_tier=trust_tier,
                actor=actor,
                local_only=local_only,
                target_is_loopback=target_is_loopback,
            )
        ).decision.value

    # -- steps ---------------------------------------------------------------

    def _require_known_tier(self, request: PolicyRequest) -> None:
        if request.trust_tier not in self.matrix.tiers():
            raise MalformedPolicyState(
                f"unknown trust tier {request.trust_tier!r}; a tier is never "
                "inferred or defaulted",
                source=_SOURCE,
            )

    def _absolute_rule(
        self, rule: OperationClassRule, request: PolicyRequest
    ) -> PolicyDecisionRecord | None:
        """Rules that decide on their own, before the tier matrix is consulted."""
        if rule.is_always_denied:
            return self._record(
                request, Decision.DENY, rule.name,
                "fixed rule DENY for every actor, always", None,
            )
        if rule.fixed == "RECOVERY_SUPERVISOR_ONLY":
            return self._rollback_rule(rule, request)
        return None

    def _rollback_rule(
        self, rule: OperationClassRule, request: PolicyRequest
    ) -> PolicyDecisionRecord:
        """ROLLBACK_STABLE is DENY at Phase 4, for every actor including the invoker.

        The canonical set carves out exactly one exception: `lifecycle.recovery`
        invoking a verified Recovery Supervisor, which is Phase 22B. Granting
        anything to that invoker now would grant it to a component that does not
        exist and whose canonical preconditions - verified immutable target, no
        transformation, evidence emitted - cannot be checked. The invoker is
        still read from authority so the reason names it, and so this decision
        follows the map if the map ever changes.
        """
        invoker = self.authority.rollback_invoker
        detail = (
            f"only {invoker} may ever invoke this, and only through a verified "
            "Recovery Supervisor (Phase 22B), which is not implemented"
        )
        return self._record(
            request, Decision.DENY, rule.name,
            f"fixed rule RECOVERY_SUPERVISOR_ONLY; {detail}", None,
        )

    def _base_decision(
        self, rule: OperationClassRule, request: PolicyRequest
    ) -> tuple[Decision, str]:
        if request.local_only and rule.denied_in_local_only:
            return Decision.DENY, "Local-Only: outbound external path is DENY"
        resolution = self.matrix.resolution(rule.name, request.trust_tier)
        return resolution.decision, f"tier matrix {request.trust_tier}"

    def _apply_narrowing(
        self,
        decision: Decision,
        why: str,
        rule: OperationClassRule,
        request: PolicyRequest,
    ) -> tuple[Decision, str]:
        """Fixed rules that may only make the decision stricter."""
        for narrowed, note in self._narrowing_rules(rule, request):
            if narrowed is not None:
                before = decision
                decision = _narrow(decision, narrowed)
                if decision is not before:
                    why = f"{why}; {note}"
        if rule.never_auto and decision is Decision.AUTO:
            decision = Decision.ASK_USER
            why = f"{why}; fixed rule forbids AUTO"
        if request.requires_execution and not request.isolation_satisfied:
            decision = _narrow(decision, Decision.DENY)
            why = f"{why}; required isolation properties unsatisfiable"
        return decision, why

    @staticmethod
    def _narrowing_rules(
        rule: OperationClassRule, request: PolicyRequest
    ) -> list[tuple[Decision | None, str]]:
        """Each fixed rule that constrains a stated fact. Unstated fact = refuse."""
        found: list[tuple[Decision | None, str]] = []
        if rule.fixed == "LOOPBACK_ONLY" and request.target_is_loopback is not True:
            found.append((Decision.DENY, "fixed rule LOOPBACK_ONLY: target not loopback"))
        if rule.fixed == "OWN_PROCESS_ONLY" and request.target_is_own_process is not True:
            found.append((Decision.DENY, "fixed rule OWN_PROCESS_ONLY: not own process"))
        if rule.fixed == "LOCKFILE_BOUND" and request.lockfile_bound is not True:
            found.append((Decision.ASK_USER, "fixed rule LOCKFILE_BOUND: not lockfile-bound"))
        if (
            rule.fixed == "NEVER_AUTO_OUTSIDE_PREAUTHORIZED_SCOPE"
            and request.within_preauthorized_scope is not True
        ):
            found.append((Decision.DENY, "ACCESS_SECRET outside pre-authorized scope"))
        return found

    def _required_gate(
        self, rule: OperationClassRule, request: PolicyRequest
    ) -> str | None:
        fixed = rule.fixed or ""
        if not fixed.startswith("HUMAN_GATE_"):
            return None
        gate = "_".join(fixed.split("_")[:3])
        if gate not in self.authority.human_gates:
            raise MalformedPolicyState(
                f"fixed rule names {gate!r}, which the authority map does not "
                "declare",
                source=_SOURCE,
            )
        if "ON_REAL_OR_STABLE_DATA" in fixed and not request.targets_real_or_stable_data:
            return None
        return gate

    @staticmethod
    def _record(
        request: PolicyRequest,
        decision: Decision,
        rule: str,
        reason: str,
        gate: str | None,
    ) -> PolicyDecisionRecord:
        return PolicyDecisionRecord(
            operation_class=request.operation_class,
            trust_tier=request.trust_tier,
            actor=request.actor,
            decision=decision,
            rule=rule,
            reason=reason,
            required_human_gate=gate,
            authoritative_source=_SOURCE,
        )
