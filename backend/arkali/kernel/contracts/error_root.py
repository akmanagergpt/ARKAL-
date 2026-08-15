"""C-01 canonical error taxonomy — the root, shared by every seam below it.

Owner: kernel.contracts.

WHY THIS MODULE EXISTS. `error_base.py` and `contract_violation_base.py` both
need `ArkaliError` to derive from. Either one importing the other to get it
would be circular — `error_base.py` re-exports `ContractViolation` for its
fifteen existing importers, and `contract_violation_base.py` exists precisely
so a new consumer can reach `ContractViolation` without adding to
`error_base.py`'s fan-in. The root has no seam left to hide behind, so it
lives one level down from both, imported by each and importing neither.
"""

from __future__ import annotations


class ArkaliError(Exception):
    """Base of the canonical error taxonomy."""

    code: str = "ARK-ERR-0000"

    def __init__(self, message: str, *, source: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.source = source

    def __str__(self) -> str:
        base = f"[{self.code}] {self.message}"
        return f"{base} (source: {self.source})" if self.source else base
