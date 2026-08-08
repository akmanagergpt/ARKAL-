"""C-07 policy decision request / response (ARK-REQ-0097).

Owner: control.policy (Protected Core).

The request carries every fact the PDP is allowed to consider. It does not carry
a proposed decision, and there is no field a caller can set to influence the
outcome directly - a caller supplies facts, the PDP supplies the decision.

WHY ISOLATION POSTURE IS AN INPUT. `SECURITY_ARCHITECTURE.md` §1 shows the PDP
reading `control.isolation`. Both contexts sit in the `control` layer and
`AUTHORITY_MAP.yaml` sets `allow_same_layer: false` with no sibling edge between
them, so a direct import would be an architecture violation. The posture is
therefore resolved by `control.isolation` and injected here as a fact. The PDP
stays pure and deterministic, and the layering rule is respected rather than
quietly broken.

TRI-STATE FACTS. Fields such as `target_is_loopback` are `bool | None`. `None`
means "not stated", and a fixed rule that needs the fact refuses rather than
assuming the permissive value. Defaulting an unstated fact to True is exactly
how a fail-closed system becomes fail-open.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arkali.control.policy.operation_class import Decision


class PolicyRequest(BaseModel):
    """One governed operation, described as facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation_class: str
    trust_tier: str
    actor: str

    #: Canonical policy mode. When true every outbound external path is DENY.
    local_only: bool = False

    #: Facts consumed by specific fixed rules. `None` = not stated.
    target_is_loopback: bool | None = None
    target_is_own_process: bool | None = None
    within_preauthorized_scope: bool | None = None
    lockfile_bound: bool | None = None
    targets_real_or_stable_data: bool | None = None

    #: Resolved by control.isolation and injected. False means the tier's
    #: required properties are not all satisfiable on this host.
    isolation_satisfied: bool = True

    #: Whether the operation actually needs to execute under the tier.
    requires_execution: bool = True

    #: Human gates with a recorded decision. Never inferred by the PDP.
    recorded_human_gates: tuple[str, ...] = ()


class PolicyDecisionRecord(BaseModel):
    """The deterministic answer, with the rule that produced it.

    Every decision is audited, including AUTO (SECURITY_ARCHITECTURE.md §1), so
    `rule` and `reason` are part of the contract rather than debug text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation_class: str
    trust_tier: str
    actor: str
    decision: Decision
    rule: str
    reason: str
    required_human_gate: str | None = None
    authoritative_source: str = ""

    @property
    def permits_execution(self) -> bool:
        """ASK_USER is not permission. Only AUTO permits without a human."""
        return self.decision is Decision.AUTO

    def render(self) -> str:
        gate = f" gate={self.required_human_gate}" if self.required_human_gate else ""
        return (
            f"{self.decision.value} {self.operation_class}@{self.trust_tier} "
            f"actor={self.actor} rule={self.rule}{gate}"
        )
