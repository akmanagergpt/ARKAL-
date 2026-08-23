"""The one shared finding type every `engineering.factory` check emits.

Owner: `engineering.factory`. Moved out of `product_preflight.py`
(ADR-0008 decomposition, not a GATE 8 exception): this session's own
repeated per-stage check splits (`frontend_client_call_preflight.py`,
`frontend_root_route_preflight.py`, `frontend_route_shadowing_preflight.py`,
`backend_stage_preflight.py`, ...) each needed nothing from
`product_preflight.py` but this one small type, and each new module
added its own direct import edge to it — the real, measured
`max_fan_in_per_module` ceiling (15) was hit purely from that pattern,
with zero behavior difference either way. A leaf module holding only the
shared type lets every narrow check module depend on the type without
coupling to `product_preflight.py`'s own, much heavier orchestration
surface (`inspect_product_files`, dependency-resolution reconciliation).
`product_preflight.py` itself imports `SemanticFinding` from here too, so
every existing `from product_preflight import SemanticFinding` caller
that also needs one of that module's other names keeps working
unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SemanticFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    path: str
    detail: str
