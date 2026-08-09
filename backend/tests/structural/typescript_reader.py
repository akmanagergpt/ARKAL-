"""Minimal TypeScript reader for the frontend architecture controls.

WHY PYTHON READS TYPESCRIPT. The controls that keep the frontend honest -
ARK-REQ-0229's vertical-slice linkage, the contract-drift check, and the
no-shadow-authority checks - must compare frontend source against backend truth.
Backend truth is a live FastAPI application and a live state machine, both of
which are Python objects. Putting the comparison on the TypeScript side would
mean transcribing that truth into a fixture, and a transcribed fixture is a copy
that rots. So the comparison happens where the authority actually lives.

WHAT THIS IS NOT. Not a TypeScript parser, and it does not pretend to be. It
reads the two constructs the controls depend on - exported interfaces and the
import graph - and `strict=True` callers get an exception rather than a silent
empty result when a construct it cannot read appears. A control that quietly
found nothing would pass while proving nothing, which is the failure mode these
controls exist to prevent.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
FRONTEND: Final[pathlib.Path] = REPO / "frontend"
FRONTEND_SRC: Final[pathlib.Path] = FRONTEND / "src"
FRONTEND_TESTS: Final[pathlib.Path] = FRONTEND / "tests"

#: `export interface Name { ... }` with no nested braces. The contracts module
#: is required to stay in that shape; see `interfaces_of`.
_INTERFACE = re.compile(
    r"export\s+interface\s+(?P<name>\w+)\s*\{(?P<body>[^{}]*)\}", re.MULTILINE
)
_FIELD = re.compile(r"^\s*(?P<name>\w+)(?P<optional>\?)?\s*:\s*(?P<type>[^;]+);\s*$")
_IMPORT = re.compile(
    r"^\s*import\s+(?:type\s+)?[^'\"]*from\s+['\"](?P<module>[^'\"]+)['\"]",
    re.MULTILINE,
)
_COMMENT_LINE = re.compile(r"^\s*(//|\*|/\*)")


def sources(root: pathlib.Path) -> list[pathlib.Path]:
    """Every TypeScript source under `root`, in a stable order."""
    return sorted(
        path
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"} and path.is_file()
    )


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_comments(text: str) -> str:
    """Remove comments so a control never matches its own explanation.

    Several controls forbid a literal - a lifecycle state, an operation class -
    in production source. Those literals are named in the prose that explains
    *why* they are forbidden, and a check that matched the prose would be
    unfixable without deleting the reasoning.
    """
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_block)


def interfaces_of(path: pathlib.Path, *, strict: bool = True) -> dict[str, dict[str, str]]:
    """Exported interfaces as `{name: {field: normalised type}}`.

    An optional field (`name?: T`) is reported as `T|undefined`, so a control
    comparing against a backend schema sees the difference rather than treating
    optionality as decoration.
    """
    text = read(path)
    found: dict[str, dict[str, str]] = {}
    for match in _INTERFACE.finditer(text):
        fields: dict[str, str] = {}
        for line in match.group("body").splitlines():
            if not line.strip() or _COMMENT_LINE.match(line):
                continue
            field = _FIELD.match(line)
            if field is None:
                if strict:
                    raise AssertionError(
                        f"{path.name}: cannot read field declaration {line.strip()!r}. "
                        "The contract modules must stay in the simple shape this "
                        "control can compare against the backend."
                    )
                continue
            normalised = re.sub(r"\s+", "", field.group("type"))
            if field.group("optional"):
                normalised = f"{normalised}|undefined"
            fields[field.group("name")] = normalised
        found[match.group("name")] = fields
    if strict and not found:
        raise AssertionError(f"{path.name}: no exported interface was found")
    return found


def imports_of(path: pathlib.Path) -> list[str]:
    """Every module specifier imported by `path`."""
    return [match.group("module") for match in _IMPORT.finditer(read(path))]


def resolve(specifier: str, importer: pathlib.Path) -> pathlib.Path | None:
    """Resolve a specifier to a file under `frontend/`, or None if external.

    Handles the two forms the frontend uses: the `@/` alias declared in
    `tsconfig.json` and `vite.config.ts`, and relative paths.
    """
    if specifier.startswith("@/"):
        base = FRONTEND_SRC / specifier[2:]
    elif specifier.startswith("."):
        base = (importer.parent / specifier).resolve()
    else:
        return None
    for candidate in (
        base.with_suffix(".ts"),
        base.with_suffix(".tsx"),
        base / "index.ts",
        base / "index.tsx",
        base,
    ):
        if candidate.is_file():
            return candidate
    return None


def reachable_from(entry: pathlib.Path) -> set[pathlib.Path]:
    """Every frontend module transitively imported from `entry`, including it."""
    seen: set[pathlib.Path] = set()
    pending = [entry]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        for specifier in imports_of(current):
            target = resolve(specifier, current)
            if target is not None and target not in seen:
                pending.append(target)
    return seen
