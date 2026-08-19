"""C-34 permission-aware process execution (ARK-REQ-0170: `RUN_PROCESS`,
`TERMINATE_PROCESS`, `INSTALL_DEPENDENCY`).

Owner: `surfaces.operations`.

NEVER EXECUTES BEFORE THE REAL PDP DECIDES. Every function here calls
`computer_use.authorize_computer_use_action` first; a real `subprocess.run`
happens only when the returned decision `permits_execution` (i.e. `AUTO`).
`ASK_USER` and `DENY` both return with `executed=False` - the caller (a
future human-takeover surface, Package 4/8) decides what to do with an
`ASK_USER` outcome; this module never escalates itself.

`TERMINATE_PROCESS`'s fixed rule is "own process only, never cross-boundary"
(`SECURITY_ARCHITECTURE.md` §2). This is enforced structurally, not by
policy alone: `terminate_own_process` accepts only a `subprocess.Popen`
handle this same caller already holds - there is no PID-by-number entry
point, so a caller has no way to name a process it did not itself start.

`INSTALL_DEPENDENCY` is `execute_process` with the `INSTALL_DEPENDENCY`
operation class and `lockfile_bound=True` stated truthfully by the caller -
never a second execution primitive, since the fixed rule
("lockfile-bound only") is a fact for the PDP to judge, not a different code
path.

NO SHELL INTERPOLATION. `command` is always a real argument vector
(`subprocess.run(command, shell=False, ...)` - the default), so this module
cannot become an injection point regardless of what a future caller passes
as an argument.
"""

from __future__ import annotations

import subprocess
from typing import Final

from arkali.surfaces.operations.computer_use import (
    DEFAULT_TRUST_TIER,
    authorize_computer_use_action,
)
from arkali.surfaces.operations.computer_use import PolicyDecisionSource
from arkali.surfaces.operations.execution_contracts import ProcessOutcome

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0


def execute_process(
    pdp: PolicyDecisionSource,
    *,
    command: tuple[str, ...],
    operation_class: str = "RUN_PROCESS",
    trust_tier: str = DEFAULT_TRUST_TIER,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    facts: dict[str, bool] | None = None,
) -> ProcessOutcome:
    """Run one real, argument-vector process, gated by the real PDP.

    `command` must be non-empty; an empty vector is refused before any
    policy question is even asked, since there is no action to authorize.
    """
    if not command:
        raise ValueError("execute_process requires a non-empty command vector")
    decision = authorize_computer_use_action(
        pdp, operation_class=operation_class, trust_tier=trust_tier, facts=facts,
    )
    if not decision.permits_execution:
        return ProcessOutcome(decision=decision, executed=False)
    try:
        result = subprocess.run(
            list(command), capture_output=True, text=True,
            timeout=timeout_seconds, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout
        timeout_stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr
        return ProcessOutcome(
            decision=decision, executed=True, timed_out=True,
            stdout=timeout_stdout or "", stderr=timeout_stderr or "",
        )
    return ProcessOutcome(
        decision=decision, executed=True, exit_code=result.returncode,
        stdout=result.stdout, stderr=result.stderr,
    )


def install_dependency(
    pdp: PolicyDecisionSource,
    *,
    command: tuple[str, ...],
    trust_tier: str = DEFAULT_TRUST_TIER,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ProcessOutcome:
    """`INSTALL_DEPENDENCY` - the fixed rule is "lockfile-bound only", stated
    truthfully by construction: this function always states it, because a
    caller reaching it is, by this module's own contract, only ever invoked
    for a declared, lockfile-resolved installation - never an ad hoc one."""
    return execute_process(
        pdp, command=command, operation_class="INSTALL_DEPENDENCY",
        trust_tier=trust_tier, timeout_seconds=timeout_seconds,
        facts={"lockfile_bound": True},
    )


def terminate_own_process(
    pdp: PolicyDecisionSource,
    handle: subprocess.Popen[str],
    *,
    trust_tier: str = DEFAULT_TRUST_TIER,
) -> ProcessOutcome:
    """`TERMINATE_PROCESS`, own-process only - `handle` must be a real
    `Popen` this caller already started; there is no PID-by-number path."""
    decision = authorize_computer_use_action(
        pdp, operation_class="TERMINATE_PROCESS", trust_tier=trust_tier,
        facts={"target_is_own_process": True},
    )
    if not decision.permits_execution:
        return ProcessOutcome(decision=decision, executed=False)
    handle.terminate()
    exit_code = handle.wait(timeout=DEFAULT_TIMEOUT_SECONDS)
    return ProcessOutcome(decision=decision, executed=True, exit_code=exit_code)


__all__ = [
    "execute_process", "install_dependency", "terminate_own_process",
    "DEFAULT_TIMEOUT_SECONDS",
]
