"""Managed Product change-promotion error to HTTP-status mapping.

Owner: `surfaces.command`. Same "separate module, composed across a
same-context import" discipline as `preview_bridge_error_mapping.py` --
`error_mapping.py` is already at `max_contexts_touched_by_module`.

Only this context's OWN four local error classes appear here --
`engineering.product_change`'s real refusal types are translated into
them by the injected `_ChangePromoter` before ever reaching a route (see
`product_change_bridge.py`'s module docstring).
"""

from __future__ import annotations

from typing import Final

from arkali.surfaces.command.product_change_bridge import (
    _ChangeNotAuthorizedError,
    _ChangeStaleBaseError,
    _ChangeVerificationFailedError,
    _NoReadyChangeError,
)

PRODUCT_CHANGE_STATUS_BY_ERROR: Final[tuple[tuple[type[Exception], int], ...]] = (
    (_NoReadyChangeError, 409),
    (_ChangeVerificationFailedError, 422),
    (_ChangeStaleBaseError, 409),
    (_ChangeNotAuthorizedError, 403),
)
