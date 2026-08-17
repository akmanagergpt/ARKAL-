"""Data shapes for the migration safety sequence (ARK-REQ-0151, ARK-REQ-0336).

Owner: `lifecycle.recovery` (Protected Core).

Split from `migration_safety.py` under the module logical-line budget
(`ARCHITECTURE.md` section 8) - ADR-0008 decomposition, not an exception. This
module carries no mechanic and no policy decision, only the record shapes the
orchestrator and its steps pass between each other.
"""

from __future__ import annotations

import enum
import pathlib
from collections.abc import Callable
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine

from arkali.lifecycle.recovery.backup_service import Verifier

#: The actor this context presents to the PDP. Read by the audit trail.
ACTOR: Final[str] = "lifecycle.recovery"
#: Migration safety runs on the host with no isolation requirement.
TRUST_TIER: Final[str] = "TRUST-0"
#: The one operation class the Apply step ever requests.
APPLY_OPERATION: Final[str] = "APPLY_MIGRATION"

#: Canonical step names, in canonical order (VDC section Migration safety).
STEP_IMPACT: Final[str] = "Impact"
STEP_BACKUP: Final[str] = "Backup"
STEP_DRY_RUN: Final[str] = "Dry Run"
STEP_INTEGRITY: Final[str] = "Integrity"
STEP_CANDIDATE_MIGRATION: Final[str] = "Candidate Migration"
STEP_APPLICATION_TESTS: Final[str] = "Application Tests"
STEP_APPLY: Final[str] = "Apply"
STEP_VERIFY: Final[str] = "Verify"
STEP_ROLLBACK_POINT: Final[str] = "Rollback Point"

STEPS: Final[tuple[str, ...]] = (
    STEP_IMPACT, STEP_BACKUP, STEP_DRY_RUN, STEP_INTEGRITY,
    STEP_CANDIDATE_MIGRATION, STEP_APPLICATION_TESTS, STEP_APPLY,
    STEP_VERIFY, STEP_ROLLBACK_POINT,
)


@runtime_checkable
class HumanGateSource(Protocol):
    """The one fact the Apply step needs from governance state.

    `acceptance.engine.GovernanceState` satisfies this structurally - see
    `migration_safety.py`'s module docstring for why this is a Protocol and
    not an import.
    """

    @property
    def accepted_human_gates(self) -> frozenset[str]: ...


class MigrationStepState(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class MigrationStepResult(BaseModel):
    """One step's outcome. Every step in `STEPS` gets exactly one of these."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step: str
    state: MigrationStepState
    summary: str
    detail: str = ""


class MigrationSafetyResult(BaseModel):
    """The complete, ordered record of one migration-safety run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_revision: str
    steps: tuple[MigrationStepResult, ...]
    rollback_point_backup_id: str | None = None

    @property
    def applied(self) -> bool:
        return any(
            s.step == STEP_APPLY and s.state is MigrationStepState.PASS
            for s in self.steps
        )

    @property
    def blocked(self) -> bool:
        return any(s.state is MigrationStepState.BLOCKED for s in self.steps)

    @property
    def failed(self) -> bool:
        return any(s.state is MigrationStepState.FAIL for s in self.steps)

    def render(self) -> str:
        return " -> ".join(f"{s.step}={s.state.value}" for s in self.steps)


class MigrationSafetyRequest:
    """Every fact one migration-safety run needs, bundled by the caller.

    A plain class, not a pydantic model: `engine` and the callables are not
    serialisable, and this object never crosses a process boundary - it exists
    only to keep `MigrationSafetySequence.run` under the six-parameter budget
    (`ARCHITECTURE.md` section 8), the same reason `PolicyRequest` bundles
    facts for the PDP.
    """

    def __init__(
        self,
        *,
        engine: Engine,
        database_url: str,
        workspace: pathlib.Path,
        backup_id: str,
        application_tests: Callable[[Engine], bool],
        post_migration_verifier: Verifier,
        human_gates: HumanGateSource,
        human_actor: str,
        human_decision: str,
        human_approval_revision_hash: str,
        target_revision: str = "head",
        targets_real_or_stable_data: bool = False,
    ) -> None:
        self.engine = engine
        self.database_url = database_url
        self.workspace = workspace
        self.backup_id = backup_id
        self.application_tests = application_tests
        self.post_migration_verifier = post_migration_verifier
        self.human_gates = human_gates
        self.human_actor = human_actor
        self.human_decision = human_decision
        self.human_approval_revision_hash = human_approval_revision_hash
        self.target_revision = target_revision
        self.targets_real_or_stable_data = targets_real_or_stable_data


def remaining_blocked(done: list[MigrationStepResult]) -> list[MigrationStepResult]:
    """Every step in `STEPS` not yet attempted, recorded `BLOCKED`.

    Called once an earlier step stops the sequence, so the returned record is
    always complete over all nine steps rather than silently truncated.
    """
    started = {s.step for s in done}
    return [
        MigrationStepResult(
            step=name, state=MigrationStepState.BLOCKED,
            summary="not attempted; an earlier step stopped the sequence",
        )
        for name in STEPS if name not in started
    ]
