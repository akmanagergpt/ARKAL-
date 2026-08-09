"""Architecture gate runner.

Owner: control.architecture (Protected Core).

The runner does not decide which gates exist: it reconciles the registered gate
implementations against `architecture_gates` in AUTHORITY_MAP.yaml. A gate
declared canonically but not implemented, or implemented but not declared, is
itself a governance failure rather than a silent omission.
"""

from __future__ import annotations

import pathlib

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.authority_gates import (
    DuplicateCanonicalAuthorityGate,
    DuplicateLifecycleAuthorityGate,
    DuplicateStateMachineAuthorityGate,
    ShadowRegistryGate,
)
from arkali.control.architecture.gates.base import ArchitectureGate, GateContext
from arkali.control.architecture.gates.structure_gates import (
    ArchitectureBudgetGate,
    ForbiddenCyclesGate,
    ForbiddenDependencyDirectionGate,
    ProtectedCoreBoundaryGate,
)
from arkali.control.architecture.refusal import refuse_governance_state
from arkali.kernel.contracts.results import CheckResult, HonestState

GATE_IMPLEMENTATIONS: tuple[type[ArchitectureGate], ...] = (
    DuplicateCanonicalAuthorityGate,
    ShadowRegistryGate,
    DuplicateStateMachineAuthorityGate,
    DuplicateLifecycleAuthorityGate,
    ForbiddenDependencyDirectionGate,
    ForbiddenCyclesGate,
    ProtectedCoreBoundaryGate,
    ArchitectureBudgetGate,
)


class GateRunner:
    """Executes every canonically declared architecture gate."""

    def __init__(self, repo_root: pathlib.Path, authority_map: AuthorityMap) -> None:
        self._ctx = GateContext(repo_root, authority_map)
        self._by_id = {gate.gate_id: gate() for gate in GATE_IMPLEMENTATIONS}

    def declared_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(str(g["id"]) for g in self._ctx.authority_map.architecture_gates)
        )

    def reconcile(self) -> None:
        """Fail closed if declaration and implementation disagree."""
        declared = set(self.declared_ids())
        implemented = set(self._by_id)
        missing = sorted(declared - implemented)
        extra = sorted(implemented - declared)
        if missing:
            raise refuse_governance_state(
                f"architecture gates declared but not implemented: {missing}",
                source=self._ctx.authority_map.source_path,
            )
        if extra:
            raise refuse_governance_state(
                f"architecture gates implemented but not declared: {extra}",
                source=self._ctx.authority_map.source_path,
            )

    def run_all(self) -> tuple[CheckResult, ...]:
        """Run every declared gate in stable id order."""
        self.reconcile()
        return tuple(self._by_id[gate_id].evaluate(self._ctx)
                     for gate_id in self.declared_ids())

    @staticmethod
    def summarise(results: tuple[CheckResult, ...]) -> dict[str, int]:
        counts = {state.value: 0 for state in HonestState}
        for result in results:
            counts[result.state.value] += 1
        return {k: v for k, v in counts.items() if v}
