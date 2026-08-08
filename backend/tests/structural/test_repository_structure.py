"""Phase 1 structural tests.

These assert that the repository ENCODES the accepted architecture. They test
structure only: no capability exists yet to test, and none is simulated.

Scope boundary: the eight architecture gates and the deterministic Phase Gate
Checker belong to Phase 2 (IMPLEMENTATION_DEPENDENCY_MATRIX). Nothing here
implements them; these tests exist to prove the Phase 1 bootstrap is real and
that test discovery works.
"""

from __future__ import annotations

import importlib
import keyword
import pathlib
import pkgutil

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
AUTHORITY_MAP = REPO / "docs" / "canonical" / "AUTHORITY_MAP.yaml"

def _is_illegal_module_segment(segment: str) -> bool:
    """Generic legality test driven by Python's own keyword table."""
    return (keyword.iskeyword(segment) or keyword.issoftkeyword(segment)
            or not segment.isidentifier())


@pytest.fixture(scope="module")
def authority_map() -> dict:
    with AUTHORITY_MAP.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.mark.structural
def test_authority_map_is_readable(authority_map: dict) -> None:
    assert authority_map["schema_version"] == 1
    assert authority_map["contexts"], "no bounded contexts declared"


@pytest.mark.structural
def test_every_declared_context_directory_exists(authority_map: dict) -> None:
    """Every bounded context in the authority map has its module root on disk."""
    missing = [
        f"{name} -> {meta['module_root']}"
        for name, meta in authority_map["contexts"].items()
        if not (REPO / meta["module_root"]).is_dir()
    ]
    assert not missing, f"declared contexts without a module root: {missing}"


@pytest.mark.structural
def test_every_context_is_a_python_package(authority_map: dict) -> None:
    missing = [
        meta["module_root"]
        for meta in authority_map["contexts"].values()
        if not (REPO / meta["module_root"] / "__init__.py").is_file()
    ]
    assert not missing, f"context directories missing __init__.py: {missing}"


@pytest.mark.structural
def test_context_packages_declare_their_layer(authority_map: dict) -> None:
    """Layer/context identity is declared in code so Phase 2 gates can read it."""
    ranks = {layer["name"]: layer["rank"] for layer in authority_map["layers"]}
    mismatches: list[str] = []
    for name, meta in authority_map["contexts"].items():
        module_path = meta["module_root"].replace("backend/", "").replace("/", ".")
        try:
            mod = importlib.import_module(module_path)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            mismatches.append(f"{name}: import failed: {exc!r}")
            continue
        if getattr(mod, "__context__", None) != name:
            mismatches.append(f"{name}: __context__ = {getattr(mod, '__context__', None)!r}")
        if getattr(mod, "__layer__", None) != meta["layer"]:
            mismatches.append(f"{name}: __layer__ = {getattr(mod, '__layer__', None)!r}")
        if getattr(mod, "__layer_rank__", None) != ranks[meta["layer"]]:
            mismatches.append(f"{name}: __layer_rank__ mismatch")
        if getattr(mod, "__protected_core__", None) != meta["protected_core"]:
            mismatches.append(f"{name}: __protected_core__ mismatch")
    assert not mismatches, f"context declaration mismatches: {mismatches}"


@pytest.mark.structural
def test_every_module_root_segment_is_a_legal_python_identifier(
    authority_map: dict,
) -> None:
    """Every package path segment must be usable in an `import` statement.

    Closes Phase 1 finding F-0015 (governance erratum ERR-001). The check is
    generic: it uses Python's own keyword table rather than a hand-maintained
    word list, so it rejects any keyword, soft keyword or non-identifier.
    """
    offenders = []
    for name, meta in authority_map["contexts"].items():
        segments = meta["module_root"].split("/")
        try:
            package_segments = segments[segments.index("arkali"):]
        except ValueError:
            package_segments = segments
        bad = [s for s in package_segments if _is_illegal_module_segment(s)]
        if bad:
            offenders.append(f"{name} -> {meta['module_root']} (illegal: {bad})")
    assert not offenders, (
        "module_root segments must be legal Python identifiers usable in an "
        f"import statement: {offenders}"
    )


@pytest.mark.structural
def test_every_module_lives_inside_a_declared_bounded_context(
    authority_map: dict,
) -> None:
    """No module may exist outside its declared context (ARCHITECTURE.md 1).

    This supersedes the Phase 1 assertion that no implementation module existed
    *yet*, which was explicitly phase-scoped and which Phase 2 satisfies by
    building the governance foundation. The replacement is strictly stronger: it
    holds for every future phase instead of only the empty one, and it rejects
    orphan modules that the earlier test could never have detected.
    """
    roots = [
        REPO / meta["module_root"]
        for meta in authority_map["contexts"].values()
    ]
    grouping = {"arkali", "kernel", "control", "evidence", "execution",
                "engineering", "lifecycle", "surfaces", "registry"}
    offenders = []
    for path in (REPO / "backend" / "arkali").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py" and path.parent.name in grouping:
            continue
        if not any(root == path.parent or root in path.parents for root in roots):
            offenders.append(str(path.relative_to(REPO)).replace("\\", "/"))
    assert not offenders, f"modules outside any declared context: {offenders}"


@pytest.mark.structural
def test_package_tree_is_walkable() -> None:
    """Proves the generated tree is a real, importable package hierarchy."""
    import arkali

    found = {m.name for m in pkgutil.iter_modules(arkali.__path__)}
    expected = {"kernel", "control", "evidence", "acceptance", "execution",
                "engineering", "lifecycle", "surfaces"}
    assert expected <= found, f"missing layer packages: {expected - found}"
