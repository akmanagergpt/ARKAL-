"""Pytest bootstrap for the ARKALI backend.

Puts the backend package root on sys.path so `arkali` is importable without an
install step. Phase 1 installs nothing.
"""

from __future__ import annotations

import pathlib
import sys

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
