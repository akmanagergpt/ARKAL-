"""`HonestState` — the canonical honest-state taxonomy, standalone.

Owner: kernel.contracts.

WHY THIS MODULE EXISTS. `results.py` reached `max_fan_in_per_module` (15):
`engineering.localai` was the sixteenth context needing only the `HonestState`
enum itself, not `CheckResult`/`Finding`/`Severity`/`PROGRESSING_STATES`. The
same seam `error_base.py` -> `contract_violation_base.py` already established
for the error taxonomy applies again: decompose the real line (which contexts
need the wide governance-result model vs. which need only the state enum)
rather than adjust the ceiling, per ADR-0008.

NOTHING MOVED FOR CALLERS. `results.py` re-exports `HonestState` unchanged, so
every one of its fifteen existing importers is untouched and still receives
the identical class object. Only a new consumer needing *just* the state enum
points here instead, which is what keeps `results.py` at fan-in 15 rather than
16.

Authoritative source: CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md (Honest
states) and ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md
(Direct-AI benchmark states). The member list is fixed by the canonical set;
it is not extended here.
"""

from __future__ import annotations

import enum


class HonestState(str, enum.Enum):
    """The canonical honest-state taxonomy. No other verdict value is legal."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_TESTED = "NOT_TESTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXTERNAL_UNAVAILABLE = "EXTERNAL_UNAVAILABLE"


__all__ = ["HonestState"]
