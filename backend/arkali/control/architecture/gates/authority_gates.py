"""Gates driven purely by the declarative authority map.

Owner: control.architecture. Sources: AUTHORITY_MAP.yaml (concerns,
state_machine_authorities, lifecycle_authorities, provider_authority) and
ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md (Architecture verification).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from arkali.control.architecture.gates.base import ArchitectureGate, GateContext
from arkali.control.architecture.gates.provider_source import (
    ProviderVocabulary,
    module_paths,
    scan_module,
)
from arkali.kernel.contracts.results import CheckResult

_VDC = "VDC Architecture verification + AUTHORITY_MAP.yaml"


class DuplicateCanonicalAuthorityGate(ArchitectureGate):
    gate_id = "duplicate_canonical_authority"
    authoritative_source = _VDC

    def evaluate(self, ctx: GateContext) -> CheckResult:
        owners: dict[str, set[str]] = defaultdict(set)
        for entry in ctx.authority_map.concerns:
            owners[entry.concern].add(entry.owner)
        violations = [
            f"concern {concern!r} has {len(found)} owners: {sorted(found)}"
            for concern, found in owners.items()
            if len(found) > 1
        ]
        return self._from_violations(
            violations,
            "every concern resolves to exactly one canonical owner",
            "a concern has more than one canonical owner",
        )


class ShadowRegistryGate(ArchitectureGate):
    """A second store of a concern owned elsewhere.

    Derived from provider_authority: the map names the sole owner of the provider
    fields and forbids copying/caching by any reference-only consumer.

    TWO HALVES, ONE GATE (ARK-REQ-0053, Phase 9 Package 2). The declaration half
    below asks whether the canonical map still says what it must. The source half
    asks whether the consumers obey it, which until Package 2 nothing did -
    `docs/contracts/provider_record.md` §3 recorded that gap, and nine real
    violations were proven to pass the untouched mechanism before it was closed.
    The gate id is unchanged because `AUTHORITY_MAP.yaml` declares the gate set
    and a canonical document is not edited to accommodate an implementation.
    """

    gate_id = "shadow_registry"
    authoritative_source = _VDC + " (provider_authority) + MS Provider/Agent separation"

    def evaluate(self, ctx: GateContext) -> CheckResult:
        authority = ctx.authority_map.provider_authority
        if not authority:
            return self._from_violations(
                ["provider_authority section absent from the authority map"],
                "", "authority map does not declare provider authority",
            )
        violations = self._declaration(ctx, authority)
        source_violations, scanned = self._consumer_source(ctx, authority)
        violations.extend(source_violations)
        return self._from_violations(
            violations,
            f"provider fields have a single store; {scanned} consumer modules "
            "scanned and none stores, caches, mirrors, defaults or re-derives one",
            "a shadow registry of an externally owned concern exists",
        )

    @staticmethod
    def _declaration(ctx: GateContext, authority: dict[str, Any]) -> list[str]:
        violations: list[str] = []
        if authority.get("copying_permitted", False):
            violations.append("provider_authority.copying_permitted is true")
        if authority.get("caching_permitted", False):
            violations.append("provider_authority.caching_permitted is true")
        owner = authority.get("owner")
        consumers = authority.get("reference_only_consumers", [])
        if owner in consumers:
            violations.append(f"owner {owner!r} also listed as reference-only consumer")
        for consumer in consumers:
            if consumer not in ctx.authority_map.contexts:
                violations.append(f"unknown reference-only consumer {consumer!r}")
        return violations

    @staticmethod
    def _consumer_source(
        ctx: GateContext, authority: dict[str, Any]
    ) -> tuple[list[str], int]:
        """ARK-REQ-0053 in the source of every declared reference-only consumer.

        FAILS CLOSED. An unusable vocabulary, a consumer whose declared module
        root is not on disk, or a run that scanned nothing at all is a violation
        rather than a quiet pass - ADR-0001 treats a detector returning zero
        without a demonstrated detection as FAIL, and a scan with no subject is
        exactly that.
        """
        vocabulary = ProviderVocabulary(authority)
        if not vocabulary.usable:
            return (["provider_authority declares no owner or no owned concern"], 0)
        violations: list[str] = []
        scanned = 0
        for consumer in authority.get("reference_only_consumers", []):
            context = ctx.authority_map.contexts.get(consumer)
            if context is None:
                continue  # already reported by the declaration half
            root = ctx.repo_root / context.module_root
            paths = module_paths(root)
            if not paths:
                violations.append(
                    f"reference-only consumer {consumer!r} has no module on disk at "
                    f"{context.module_root!r}; the rule cannot be enforced over it"
                )
                continue
            for path in paths:
                scanned += 1
                violations.extend(
                    scan_module(
                        vocabulary, path, path.relative_to(ctx.repo_root).as_posix()
                    )
                )
        if scanned == 0:
            violations.append(
                "no reference-only consumer module was scanned; a PASS would be vacuous"
            )
        return (violations, scanned)


class DuplicateStateMachineAuthorityGate(ArchitectureGate):
    gate_id = "duplicate_state_machine_authority"
    authoritative_source = _VDC + " (state_machine_authorities)"

    def evaluate(self, ctx: GateContext) -> CheckResult:
        declared = ctx.authority_map.state_machine_authorities
        if not declared:
            return self._from_violations(
                ["state_machine_authorities section absent"], "", "no declaration"
            )
        violations = [
            f"entity {entity!r} names unknown context {owner!r}"
            for entity, owner in declared.items()
            if owner not in ctx.authority_map.contexts
        ]
        return self._from_violations(
            violations,
            f"{len(declared)} state machines each have exactly one authority",
            "a state machine authority is duplicated or unknown",
        )


class DuplicateLifecycleAuthorityGate(ArchitectureGate):
    gate_id = "duplicate_lifecycle_authority"
    authoritative_source = _VDC + " (lifecycle_authorities)"

    def evaluate(self, ctx: GateContext) -> CheckResult:
        declared = ctx.authority_map.lifecycle_authorities
        if not declared:
            return self._from_violations(
                ["lifecycle_authorities section absent"], "", "no declaration"
            )
        violations = [
            f"lifecycle {lifecycle!r} names unknown context {owner!r}"
            for lifecycle, owner in declared.items()
            if owner not in ctx.authority_map.contexts
        ]
        promotion = declared.get("candidate_promotion")
        rollback = declared.get("stable_rollback")
        if promotion and rollback and promotion == rollback:
            violations.append(
                f"promotion and rollback share one authority {promotion!r}; "
                "ADR-0009 requires them separated"
            )
        return self._from_violations(
            violations,
            f"{len(declared)} lifecycles each have exactly one authority",
            "a lifecycle authority is duplicated or unknown",
        )
