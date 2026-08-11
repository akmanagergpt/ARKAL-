"""C-17 phase report contract.

Owner: acceptance.engine (Protected Core).

The seventeen fields are fixed by CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md
(Phase report). A missing or empty field is a completeness failure, not a
warning: Phase Gate Checker check C1 depends on this shape.
"""

from __future__ import annotations

from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict

from arkali.acceptance.external_result import ExternalProviderResultRule
from arkali.kernel.contracts.results import HonestState

#: Canonical field order, used for stable rendering and C1 completeness.
REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "phase_id",
    "objective",
    "ark_req_ids_closed",
    "files_created",
    "files_modified",
    "public_contracts",
    "migrations",
    "state_machine_capability_changes",
    "tests_executed",
    "architecture_checks",
    "duplicate_shadow_check",
    "security_findings",
    "fake_success_scan",
    "evidence_created",
    "limitations",
    "blockers",
    "next_exact_action",
)


class TestExecutionRecord(BaseModel):
    """A test run that actually happened, with its recorded exit code.

    `exit_code` is mandatory. A claimed run without one is rejected by check C3
    rather than treated as NOT_TESTED (ARK-REQ-0210).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: This is a contract model, not a pytest class.
    __test__: ClassVar[bool] = False

    command: str
    exit_code: int
    passed: int = 0
    failed: int = 0
    summary: str = ""
    #: ARK-REQ-0219. What this run claims about an external provider, DECLARED
    #: and never inferred from `command` or `summary`.
    #:
    #: The default is the non-claiming class, so every accepted historical report
    #: stays valid and byte-identical while granting no external provenance -
    #: silence can never read as a claim. It is not a substitute for declaring:
    #: `external_result_check` distinguishes a supplied value from a default
    #: through `model_fields_set`, and a report that owes a declaration and omits
    #: one is refused.
    external_result: ExternalProviderResultRule.Declared = (
        ExternalProviderResultRule.Declared.NO_EXTERNAL_RESULT
    )


class PhaseReport(BaseModel):
    """A complete phase report. Every required field must be present."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase_id: str
    objective: str
    ark_req_ids_closed: tuple[str, ...]
    files_created: tuple[str, ...]
    files_modified: tuple[str, ...]
    public_contracts: tuple[str, ...]
    migrations: tuple[str, ...]
    state_machine_capability_changes: str
    tests_executed: tuple[TestExecutionRecord, ...]
    architecture_checks: str
    duplicate_shadow_check: str
    security_findings: str
    fake_success_scan: str
    evidence_created: tuple[str, ...]
    limitations: str
    blockers: str
    next_exact_action: str
    status: HonestState

    #: Fields that may legitimately be empty (a phase can create no migration).
    ALLOWED_EMPTY: Final[frozenset[str]] = frozenset(
        {"files_modified", "migrations", "public_contracts", "ark_req_ids_closed"}
    )

    def missing_fields(self) -> tuple[str, ...]:
        """Required fields that are absent or empty. C1 fails if non-empty."""
        missing: list[str] = []
        for field in REQUIRED_FIELDS:
            if field in self.ALLOWED_EMPTY:
                continue
            value = getattr(self, field)
            if value is None or (hasattr(value, "__len__") and len(value) == 0):
                missing.append(field)
        return tuple(missing)

    def unnamed_runs(self) -> tuple[int, ...]:
        """Indices of recorded runs with no command string (C3).

        A run with no *exit code* cannot exist at all: `exit_code` is a required
        field, so a claimed-but-unexecuted test is rejected at construction time
        rather than by a runtime check. This method covers the remaining way a
        run record can be uninformative.
        """
        return tuple(
            index
            for index, record in enumerate(self.tests_executed)
            if not record.command.strip()
        )

    def failing_runs(self) -> tuple[TestExecutionRecord, ...]:
        return tuple(r for r in self.tests_executed if r.exit_code != 0)
