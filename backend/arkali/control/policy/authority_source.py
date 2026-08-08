"""Single reader for the authoritative documents this context consumes.

Owner: control.policy (Protected Core).

WHY THIS EXISTS. Four policy modules had grown their own copy of "resolve the
path, raise if absent, parse the YAML, raise if malformed". That is four places
to change and four chances to weaken the failure behaviour independently — and it
pushed `kernel.contracts.errors` to a fan-in of 16 against a budget of 15. The
budget was pointing at real duplication, so the duplication is removed rather
than the budget waived.

Every consumer in `control.policy` now reads its authority through here, so the
fail-closed behaviour on a missing or malformed authoritative document is defined
exactly once.

This holds no governed value of its own. It reads documents; it never caches,
defaults or repairs them.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

from arkali.kernel.contracts.errors import AuthoritativeSourceError

AUTHORITY_MAP_RELPATH = "docs/canonical/AUTHORITY_MAP.yaml"
SECURITY_ARCHITECTURE_RELPATH = "docs/canonical/SECURITY_ARCHITECTURE.md"


def refuse(message: str, source: str) -> AuthoritativeSourceError:
    """Build the canonical refusal. Callers raise it; nothing here swallows one."""
    return AuthoritativeSourceError(message, source=source)


def read_text(repo_root: pathlib.Path, relpath: str) -> tuple[str, str]:
    """Return (text, resolved_path). Absent document fails closed."""
    path = repo_root / relpath
    if not path.is_file():
        raise refuse(f"authoritative document not found: {relpath}", str(path))
    return path.read_text(encoding="utf-8"), str(path)


def load_authority_map(repo_root: pathlib.Path) -> tuple[dict[str, Any], str]:
    """Parse the authority map. Malformed content fails closed."""
    text, source = read_text(repo_root, AUTHORITY_MAP_RELPATH)
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise refuse(f"authority map is not parseable YAML: {exc}", source) from exc
    if not isinstance(raw, dict):
        raise refuse("authority map root is not a mapping", source)
    return raw, source


def require_section(raw: dict[str, Any], key: str, source: str) -> Any:
    """Fetch a required top-level section, or fail closed."""
    if key not in raw or raw[key] in (None, {}, []):
        raise refuse(f"authority map declares no {key!r}", source)
    return raw[key]
