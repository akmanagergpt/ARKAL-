"""C-34 Computer-Use execution outcome value objects (ARK-REQ-0170).

Owner: `surfaces.operations`.

AN OUTCOME NEVER CLAIMS EXECUTION IT DID NOT PERFORM. `executed` is `True`
only when the wrapped primitive actually ran a real process/file operation;
an `ASK_USER`/`DENY` decision always carries `executed=False` and no
exit_code/stdout/stderr, so a caller cannot mistake "the PDP resolved a
decision" for "the action happened" (ARK-REQ-0218: no fabricated jobs).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arkali.surfaces.operations.computer_use_contracts import ComputerUseDecision


class ProcessOutcome(BaseModel):
    """The real result of one gated `RUN_PROCESS`/`INSTALL_DEPENDENCY` call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ComputerUseDecision
    executed: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class FileOutcome(BaseModel):
    """The real result of one gated `READ_FILE`/`WRITE_WORKSPACE_FILE` call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ComputerUseDecision
    executed: bool
    path: str
    content: bytes | None = None


__all__ = ["ProcessOutcome", "FileOutcome"]
