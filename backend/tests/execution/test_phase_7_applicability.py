"""ARK-REQ-0060 applicability, evaluated against real persisted registry data.

THE RULE, READ FROM THE REGISTER RATHER THAN RESTATED. Appendix A gives
`ARK-REQ-0060` the applicability rule `job_type.supports_pause == true` "in the
job-type contract registry". The rule text below is **parsed out of
`REQUIREMENT_REGISTER.md`**, so a control here cannot drift from the canonical
statement it claims to evaluate.

WHAT APPLICABILITY MEANS, AND WHAT IT DOES NOT. Governing rule 6 says every
CONDITIONAL rule is objective and machine-evaluable from recorded system state;
governing rule 7 resolves an unwaived *unevaluable* rule to APPLICABLE. Before
Package 3 the registry did not exist, so the rule was unevaluable and the
requirement was APPLICABLE by rule 7. It is now evaluable — and it evaluates to
**true**, because a job type declaring `supports_pause = true` exists and is
persisted.

**A type that does not support pause does not make the requirement
NOT_APPLICABLE.** The rule is satisfied by the existence of a pausable job type,
not by every type being pausable; reading it the other way would let a single
unpausable registration retire a MANDATORY-in-effect obligation, which is
exactly the scope-narrowing exploit governing rule 6 exists to prevent. Both
sides are proven below.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from arkali.execution.durable.errors import PauseNotSupported, UnknownJobType
from arkali.execution.durable.records import JobTypeRecord
from tests.execution.phase_7_harness import (  # noqa: F401 - fixtures
    JOB_ID,
    JOB_TYPE,
    OWNER,
    UNPAUSABLE_TYPE,
    MovableClock,
    Runtime,
    clock,
    database,
    enqueue_body,
    pdp,
    runtime,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
REGISTER = REPO / "docs" / "canonical" / "REQUIREMENT_REGISTER.md"


def canonical_rule() -> str:
    """The Appendix A rule text for ARK-REQ-0060, parsed from the register."""
    for line in REGISTER.read_text(encoding="utf-8").splitlines():
        if line.startswith("| ARK-REQ-0060 |") and "supports_pause" in line:
            return [c.strip() for c in line.strip("|").split("|")][1]
    raise AssertionError("no Appendix A rule found for ARK-REQ-0060")


class TestTheRuleIsWhatTheRegisterSays:
    def test_the_rule_names_the_registry_field_this_package_built(self) -> None:
        rule = canonical_rule()
        assert "supports_pause" in rule
        assert "job_type" in rule
        assert "registry" in rule.lower()

    def test_the_field_the_rule_names_is_a_real_persisted_column(self) -> None:
        """The bridge from canonical text to schema, asserted not assumed."""
        field = re.search(r"`job_type\.(\w+)\s*==", canonical_rule())
        assert field is not None, f"cannot parse a field from {canonical_rule()!r}"
        columns = {c.name for c in JobTypeRecord.__table__.columns}
        assert field.group(1) in columns, (
            f"the rule reads {field.group(1)!r}, which the registry does not store"
        )

    def test_the_requirement_is_conditional_and_owned_by_execution_durable(
        self,
    ) -> None:
        row = next(
            line for line in REGISTER.read_text(encoding="utf-8").splitlines()
            if line.startswith("| ARK-REQ-0060 |") and "supports_pause" not in line
        )
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[3] == "CONDITIONAL"
        assert cells[4] == "7"
        assert cells[5] == "execution.durable"


class TestTheRuleEvaluatesTrueAgainstRealData:
    def test_a_pausable_type_makes_the_rule_true(self, runtime: Runtime) -> None:
        """Evaluated by reading the persisted row, not by asserting a constant."""
        with runtime.durable() as (recovery, _execution, _session):
            recovery.job_types.declare(JOB_TYPE, supports_pause=True)
        with runtime.durable() as (recovery, _execution, _session):
            assert recovery.job_types.supports_pause(JOB_TYPE) is True, (
                "the applicability rule does not evaluate true against the "
                "persisted registry"
            )

    def test_the_answer_survives_a_restart(self, runtime: Runtime) -> None:
        """An applicability answer held only in memory would be worthless."""
        with runtime.durable() as (recovery, _execution, _session):
            recovery.job_types.declare(JOB_TYPE, supports_pause=True)
            recovery.job_types.declare(UNPAUSABLE_TYPE, supports_pause=False)
        for _restart in range(3):
            with runtime.durable() as (recovery, _execution, _session):
                assert recovery.job_types.supports_pause(JOB_TYPE) is True
                assert recovery.job_types.supports_pause(UNPAUSABLE_TYPE) is False

    def test_an_unpausable_type_does_not_retire_the_requirement(
        self, runtime: Runtime
    ) -> None:
        """THE SCOPE-NARROWING EXPLOIT, refused.

        Both types coexist. The rule still evaluates true, because a pausable
        job type exists — so `ARK-REQ-0060` remains APPLICABLE and Phase 7 still
        owes pause/resume evidence. If applicability were read as "every type",
        one unpausable registration would silently retire the obligation.
        """
        with runtime.durable() as (recovery, _execution, _session):
            recovery.job_types.declare(JOB_TYPE, supports_pause=True)
            recovery.job_types.declare(UNPAUSABLE_TYPE, supports_pause=False)
        with runtime.durable() as (recovery, _execution, _session):
            declared = recovery.job_types.declared()
            pausable = [t for t in declared if t.supports_pause]
            assert len(declared) == 2
            assert pausable, (
                "no pausable type exists, so the rule would not evaluate true"
            )
            assert recovery.job_types.supports_pause(JOB_TYPE) is True


class TestBothSidesOfTheRuleAreEnforced:
    def _enqueue(self, runtime: Runtime, job_type: str, job_id: str) -> None:
        with runtime.app() as client:
            response = client.post(
                "/api/jobs",
                json=enqueue_body(
                    job_id=job_id, job_type=job_type, idempotency_key=job_id
                ),
            )
            assert response.status_code == 202
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(job_id, OWNER)

    def test_supports_pause_true_permits_pause_and_resume(
        self, runtime: Runtime
    ) -> None:
        with runtime.durable() as (recovery, _execution, _session):
            recovery.job_types.declare(JOB_TYPE, supports_pause=True)
        self._enqueue(runtime, JOB_TYPE, "JOB-PAUSABLE")
        with runtime.durable() as (recovery, _execution, _session):
            assert recovery.pause("JOB-PAUSABLE").lifecycle_state == "PAUSED"
        with runtime.durable() as (recovery, execution, _session):
            assert recovery.resume("JOB-PAUSABLE").lifecycle_state == "RUNNING"
            assert execution.attempt_count("JOB-PAUSABLE") == 1

    def test_supports_pause_false_refuses_pause(self, runtime: Runtime) -> None:
        with runtime.durable() as (recovery, _execution, _session):
            recovery.job_types.declare(UNPAUSABLE_TYPE, supports_pause=False)
        self._enqueue(runtime, UNPAUSABLE_TYPE, "JOB-UNPAUSABLE")
        with runtime.durable() as (recovery, execution, _session):
            with pytest.raises(PauseNotSupported):
                recovery.pause("JOB-UNPAUSABLE")
            assert execution.jobs.require(
                "JOB-UNPAUSABLE"
            ).lifecycle_state == "RUNNING", "a refused pause moved the job"

    def test_an_undeclared_type_fails_closed_rather_than_defaulting(
        self, runtime: Runtime
    ) -> None:
        """An absent row is an unanswered question, not a `false`."""
        self._enqueue(runtime, "arkali.phase7.undeclared", "JOB-UNDECLARED")
        with runtime.durable() as (recovery, execution, _session):
            with pytest.raises(UnknownJobType):
                recovery.pause("JOB-UNDECLARED")
            assert execution.jobs.require(
                "JOB-UNDECLARED"
            ).lifecycle_state == "RUNNING"

    def test_recovery_is_unaffected_by_pause_capability(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """Crash recovery is a durability property, not the pause path.

        An unpausable job must still be recovered, or `ARK-REQ-0059` would be
        conditional on `ARK-REQ-0060` — which no canonical statement says.
        """
        with runtime.durable() as (recovery, _execution, _session):
            recovery.job_types.declare(UNPAUSABLE_TYPE, supports_pause=False)
        self._enqueue(runtime, UNPAUSABLE_TYPE, "JOB-UNPAUSABLE-2")
        clock.advance(61)
        with runtime.durable() as (recovery, execution, _session):
            assert recovery.recover_lost_executions() == ("JOB-UNPAUSABLE-2",)
            assert execution.jobs.require(
                "JOB-UNPAUSABLE-2"
            ).lifecycle_state == "RESUMING"
