"""C-34 permission-aware process execution (ARK-REQ-0170): real subprocess
execution, gated by the real PDP, never bypassed.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

import pytest
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.surfaces.operations.process_boundary import (
    execute_process,
    install_dependency,
    terminate_own_process,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


class _AlwaysAskUser:
    def decide_computer_use(self, **_kwargs: object) -> tuple[str, str, str | None]:
        return "ASK_USER", "fixture always asks", None


class _AlwaysDeny:
    def decide_computer_use(self, **_kwargs: object) -> tuple[str, str, str | None]:
        return "DENY", "fixture always denies", None


class TestExecuteProcessOnlyRunsWhenTheRealPdpGrantsAuto:
    def test_a_real_harmless_command_actually_runs_at_trust_1(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        outcome = execute_process(
            pdp, command=(sys.executable, "-c", "print('arkali-computer-use-ok')"),
            trust_tier="TRUST-1",
        )
        assert outcome.decision.permits_execution
        assert outcome.executed
        assert outcome.exit_code == 0
        assert "arkali-computer-use-ok" in outcome.stdout

    def test_a_nonzero_exit_is_reported_honestly(self, pdp: PolicyDecisionPoint) -> None:
        outcome = execute_process(
            pdp, command=(sys.executable, "-c", "import sys; sys.exit(7)"),
            trust_tier="TRUST-1",
        )
        assert outcome.executed
        assert outcome.exit_code == 7

    def test_an_ask_user_decision_never_executes(self) -> None:
        outcome = execute_process(
            _AlwaysAskUser(), command=(sys.executable, "-c", "print('should not run')"),
        )
        assert not outcome.executed
        assert outcome.exit_code is None
        assert outcome.stdout == ""

    def test_a_deny_decision_never_executes(self) -> None:
        outcome = execute_process(
            _AlwaysDeny(), command=(sys.executable, "-c", "print('should not run')"),
        )
        assert not outcome.executed

    def test_an_empty_command_is_refused_before_any_policy_question(self) -> None:
        with pytest.raises(ValueError):
            execute_process(_AlwaysDeny(), command=())

    def test_install_system_software_is_never_auto_at_any_tier(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        for tier in ("TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"):
            outcome = execute_process(
                pdp, command=(sys.executable, "--version"),
                operation_class="INSTALL_SYSTEM_SOFTWARE", trust_tier=tier,
            )
            assert not outcome.executed, f"tier {tier} let INSTALL_SYSTEM_SOFTWARE auto-run"


class TestInstallDependencyStatesLockfileBoundTruthfully:
    def test_lockfile_bound_install_is_auto_at_trust_1(self, pdp: PolicyDecisionPoint) -> None:
        outcome = install_dependency(pdp, command=(sys.executable, "-c", "print('installed')"))
        assert outcome.decision.permits_execution
        assert outcome.executed
        assert "installed" in outcome.stdout


class TestTerminateOwnProcessHasNoPidByNumberPath:
    def test_a_real_long_running_process_is_really_terminated(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        handle = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
        )
        try:
            outcome = terminate_own_process(pdp, handle, trust_tier="TRUST-1")
            assert outcome.decision.permits_execution
            assert outcome.executed
            time.sleep(0.2)
            assert handle.poll() is not None
        finally:
            if handle.poll() is None:
                handle.kill()
                handle.wait()

    def test_a_deny_decision_leaves_the_process_running(self) -> None:
        handle = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            outcome = terminate_own_process(_AlwaysDeny(), handle)
            assert not outcome.executed
            assert handle.poll() is None
        finally:
            handle.kill()
            handle.wait()
