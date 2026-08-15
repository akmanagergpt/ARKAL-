"""C-01 canonical error taxonomy — the contract-violation seam.

Owner: kernel.contracts.

WHY THIS MODULE EXISTS. `error_base.py` itself reached `max_fan_in_per_module`
(15): `engineering.repair` was the sixteenth context needing a base to derive
from. Its own docstring already named the shape of this problem - "the count
only ever grows" - so ADR-0008 decomposition applies a second time, to the
module decomposition previously created to relieve `errors.py`.

THE SEAM IS REAL, NOT ARITHMETIC. `error_base.py` groups four bases along one
line (contract-violation against governance-state), the same line that already
separates what a context *raises about a value it was handed* from what a
context *raises about governance data it tried to read*. `ContractViolation`
moves; the root and the two governance-state bases stay, because nothing
outside a value contract has needed this class yet.

NOTHING MOVED FOR CALLERS. `error_base.py` re-exports `ContractViolation`
unchanged, so every one of its fifteen existing importers is untouched and
still receives the identical class object. Only a new consumer needing
*just* the contract-violation base points here instead, which is what keeps
`error_base.py` at fan-in 15 rather than 16.

THE ROOT COMES FROM `error_root.py`, NOT `error_base.py`. `error_base.py`
itself re-exports this module's `ContractViolation`, so importing
`error_base` here to reach `ArkaliError` would be circular. Both this module
and `error_base.py` import the shared root instead of each other.

Rule, unchanged: no error type in this taxonomy may be caught and converted
into a PASS.
"""

from __future__ import annotations

from arkali.kernel.contracts.error_root import ArkaliError


class ContractViolation(ArkaliError):
    """A value does not satisfy its declared contract."""

    code = "ARK-ERR-0001"
