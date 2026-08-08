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
import pathlib
import pkgutil

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
AUTHORITY_MAP = REPO / "docs" / "canonical" / "AUTHORITY_MAP.yaml"

PY_KEYWORD_SEGMENTS = {"import", "class", "def", "return", "from", "global",
                       "lambda", "pass", "raise", "try", "with", "yield",
                       "assert", "async", "await", "break", "continue", "del",
                       "elif", "else", "except", "finally", "for", "if", "in",
                       "is", "none", "nonlocal", "not", "or", "and", "while"}


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
def test_no_context_module_root_uses_a_python_keyword(authority_map: dict) -> None:
    """A path segment that is a Python keyword cannot be reached by `import`.

    Recorded as Phase 1 finding F-0015. This test is expected to FAIL until the
    accepted AUTHORITY_MAP is amended through the governance path; it is not
    skipped, xfailed or weakened, because doing so would hide a real defect.
    """
    offenders = [
        f"{name} -> {meta['module_root']}"
        for name, meta in authority_map["contexts"].items()
        if any(seg.lower() in PY_KEYWORD_SEGMENTS
               for seg in meta["module_root"].split("/"))
    ]
    assert not offenders, (
        "module roots containing a Python reserved keyword cannot be imported "
        f"with an import statement: {offenders}"
    )


@pytest.mark.structural
def test_no_context_package_contains_implementation_yet() -> None:
    """Phase 1 creates structure only: context packages hold no modules."""
    pkg_root = REPO / "backend" / "arkali"
    offenders = [
        str(p.relative_to(REPO)).replace("\\", "/")
        for p in pkg_root.rglob("*.py")
        if p.name != "__init__.py"
    ]
    assert not offenders, f"Phase 1 must not implement modules: {offenders}"


@pytest.mark.structural
def test_package_tree_is_walkable() -> None:
    """Proves the generated tree is a real, importable package hierarchy."""
    import arkali

    found = {m.name for m in pkgutil.iter_modules(arkali.__path__)}
    expected = {"kernel", "control", "evidence", "acceptance", "execution",
                "engineering", "lifecycle", "surfaces"}
    assert expected <= found, f"missing layer packages: {expected - found}"
