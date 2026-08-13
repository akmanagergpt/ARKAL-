"""Policy-owned actor boundaries for Phase 13 acceptance infrastructure.

The register owns requirement identity and classification; this module accepts
those facts from that authority and never parses, copies, or reinterprets them.
It owns only the policy answer to an attempted action.  Automated actors are
derived from ``stable_mutation.prohibited_actors`` and human gates from the
canonical authority map on every load.

This is deliberately not an Acceptance Engine.  It issues no requirement,
phase, acceptance, or release verdict.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterable
from typing import Any

from arkali.control.policy.authority_source import (
    load_authority_map,
    refuse,
    require_section,
)
from arkali.control.policy.policy_errors import (
    CanonicalRequirementMutation,
    HumanGateNotRecorded,
    ProtectedCoreMutation,
)


def _labels(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(str(item).strip().lower() for item in value if str(item).strip())


class AcceptanceBoundaryPolicy:
    """Refuse automated actors crossing canonical acceptance boundaries."""

    def __init__(
        self,
        automated_actors: frozenset[str],
        human_gates: frozenset[str],
        applicability_waiver_gate: str,
        source: str,
    ) -> None:
        self._automated = automated_actors
        self._human_gates = human_gates
        self._waiver_gate = applicability_waiver_gate
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> AcceptanceBoundaryPolicy:
        raw, source = load_authority_map(repo_root)
        mutation: Any = require_section(raw, "stable_mutation", source)
        gates: Any = require_section(raw, "human_gates", source)
        if not isinstance(mutation, dict) or not isinstance(gates, dict):
            raise refuse("policy boundary declarations must be mappings", source)
        actors = _labels(mutation.get("prohibited_actors"))
        declared_gates = frozenset(str(gate).strip() for gate in gates if str(gate).strip())
        waiver = tuple(
            gate for gate, description in gates.items()
            if "applicability waiver" in str(description).strip().lower()
        )
        if not actors:
            raise refuse("no automated/prohibited actors are declared", source)
        if not declared_gates or len(waiver) != 1:
            raise refuse(
                "exactly one exceptional applicability-waiver human gate is required",
                source,
            )
        return cls(actors, declared_gates, waiver[0], source)

    def automated_actors(self) -> tuple[str, ...]:
        return tuple(sorted(self._automated))

    def human_gates(self) -> tuple[str, ...]:
        return tuple(sorted(self._human_gates))

    def assert_may_author_applicability(self, actor: str) -> None:
        """Evaluation is allowed; authorship, amendment and classification are not."""
        if actor.strip().lower() in self._automated:
            raise CanonicalRequirementMutation(
                f"{actor!r} may evaluate register applicability but may not author, "
                "amend, broaden, reinterpret, or classify it",
                source=self.source,
            )

    def assert_may_originate_not_applicable(self, actor: str) -> None:
        """An implementing actor never originates NOT_APPLICABLE."""
        if actor.strip().lower() in self._automated:
            raise CanonicalRequirementMutation(
                f"{actor!r} may not originate NOT_APPLICABLE; the classification "
                "must come from the Canonical Requirement Register",
                source=self.source,
            )

    def assert_may_waive(
        self,
        *,
        actor: str,
        mandatory: bool,
        recorded_human_gates: Iterable[str] = (),
    ) -> None:
        """Protect MANDATORY entries and the human-owned exceptional waiver."""
        normal_actor = actor.strip().lower()
        if normal_actor in self._automated:
            raise CanonicalRequirementMutation(
                f"{actor!r} may never waive a requirement"
                + ("; it is MANDATORY" if mandatory else ""),
                source=self.source,
            )
        recorded = frozenset(recorded_human_gates)
        if self._waiver_gate not in recorded:
            raise HumanGateNotRecorded(
                f"an exceptional applicability waiver requires {self._waiver_gate}",
                source=self.source,
            )

    def assert_may_weaken_acceptance(self, actor: str) -> None:
        if actor.strip().lower() in self._automated:
            raise ProtectedCoreMutation(
                f"{actor!r} may not weaken, relax, disable, or re-scope "
                "requirements or acceptance to obtain PASS",
                source=self.source,
            )

    def assert_machine_gate_boundary(
        self, *, required_gate: str | None, recorded_human_gates: Iterable[str]
    ) -> None:
        """A machine verdict cannot substitute for any canonical human gate."""
        if required_gate is None:
            return
        if required_gate not in self._human_gates:
            raise HumanGateNotRecorded(
                f"unknown required human gate {required_gate!r}; refusing to infer it",
                source=self.source,
            )
        if required_gate not in frozenset(recorded_human_gates):
            raise HumanGateNotRecorded(
                f"machine verdict cannot supersede required {required_gate}",
                source=self.source,
            )
