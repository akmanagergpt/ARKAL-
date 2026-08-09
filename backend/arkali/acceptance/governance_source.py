"""Single reader for the governance documents acceptance.engine consumes.

Owner: acceptance.engine (Protected Core).

WHY THIS EXISTS. Four acceptance modules had each grown their own "resolve the
path, raise if absent, parse, raise if malformed", and the fifth pushed
`kernel.contracts.errors` to a fan-in of 16 against a budget of 15. The budget
was pointing at real duplication: four places to change, and four chances to
weaken the fail-closed behaviour independently. Removing it is the fix; waiving
the budget would have preserved the duplication.

Every consumer in `acceptance.engine` now reads its authority through here, so
the behaviour on a missing or unreadable governance document is defined once.

This holds no governed value. It reads documents; it never caches, defaults or
repairs them.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from arkali.kernel.contracts.errors import AuthoritativeSourceError


def refuse(message: str, source: str) -> AuthoritativeSourceError:
    """Build the canonical refusal. Callers raise it; nothing here swallows one."""
    return AuthoritativeSourceError(message, source=source)


def read_document(repo_root: pathlib.Path, relpath: str) -> tuple[str, str]:
    """Return (text, resolved path). An absent document fails closed."""
    path = repo_root / relpath
    if not path.is_file():
        raise refuse(f"governance document not found: {relpath}", str(path))
    return path.read_text(encoding="utf-8"), str(path)


def read_json(repo_root: pathlib.Path, relpath: str) -> tuple[Any, str]:
    """Parse a governance JSON artifact. Malformed content fails closed."""
    text, source = read_document(repo_root, relpath)
    try:
        return json.loads(text), source
    except json.JSONDecodeError as exc:
        raise refuse(f"{relpath} is not parseable JSON: {exc}", source) from exc
