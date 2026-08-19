"""SBOM / dependency inventory (ARK-REQ-0124 partial, ARK-REQ-0369, Phase 26
Package 3). Driven against this repository's own real, live manifests - no
fixture file stands in for `backend/pyproject.toml` or
`frontend/package.json`.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import tomllib

from arkali.lifecycle.release.sbom import (
    DependencyEntry,
    PACKAGE_JSON_RELPATH,
    PYPROJECT_RELPATH,
    SbomError,
    SoftwareBillOfMaterials,
    generate_sbom,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


class TestGenerateSbom:
    def test_returns_a_real_bill_of_materials(self) -> None:
        sbom = generate_sbom(REPO)
        assert isinstance(sbom, SoftwareBillOfMaterials)
        assert len(sbom.entries) > 0

    def test_covers_every_real_python_production_dependency(self) -> None:
        with (REPO / PYPROJECT_RELPATH).open("rb") as handle:
            declared = set((tomllib.load(handle)["project"])["dependencies"])
        sbom = generate_sbom(REPO)
        found = {
            f"{e.name}{e.version_constraint}" for e in sbom.entries if e.ecosystem == "python"
        }
        assert len(found) == len(declared)
        for raw in declared:
            name = raw.split(">=")[0].split("==")[0].strip()
            assert any(e.name == name and e.ecosystem == "python" for e in sbom.entries)

    def test_covers_every_real_node_production_dependency(self) -> None:
        declared = json.loads((REPO / PACKAGE_JSON_RELPATH).read_text(encoding="utf-8"))
        declared_names = set(declared["dependencies"].keys())
        sbom = generate_sbom(REPO)
        found_names = {e.name for e in sbom.entries if e.ecosystem == "node"}
        assert found_names == declared_names

    def test_never_includes_node_dev_dependencies(self) -> None:
        declared = json.loads((REPO / PACKAGE_JSON_RELPATH).read_text(encoding="utf-8"))
        dev_names = set(declared["devDependencies"].keys())
        sbom = generate_sbom(REPO)
        found_names = {e.name for e in sbom.entries}
        assert not (dev_names & found_names), "dev-only tooling is not SBOM material"

    def test_is_deterministic_across_calls(self) -> None:
        first = generate_sbom(REPO)
        second = generate_sbom(REPO)
        assert first == second

    def test_entries_are_sorted_by_ecosystem_then_name(self) -> None:
        sbom = generate_sbom(REPO)
        keys = [(e.ecosystem, e.name) for e in sbom.entries]
        assert keys == sorted(keys)

    def test_refuses_a_missing_python_manifest(self, tmp_path: pathlib.Path) -> None:
        empty = tmp_path / "no_repo"
        (empty / "frontend").mkdir(parents=True)
        (empty / "frontend" / "package.json").write_text(
            json.dumps({"dependencies": {}}), encoding="utf-8"
        )
        with pytest.raises(SbomError):
            generate_sbom(empty)

    def test_refuses_a_missing_node_manifest(self, tmp_path: pathlib.Path) -> None:
        empty = tmp_path / "no_frontend"
        (empty / "backend").mkdir(parents=True)
        (empty / "backend" / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi>=0.115"]\n', encoding="utf-8"
        )
        with pytest.raises(SbomError):
            generate_sbom(empty)

    def test_parses_a_pep508_constraint_correctly(self, tmp_path: pathlib.Path) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text(
            '[project]\ndependencies = ["widget>=1.2.3", "gadget"]\n', encoding="utf-8"
        )
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(json.dumps({"dependencies": {}}), encoding="utf-8")
        sbom = generate_sbom(tmp_path)
        widget = next(e for e in sbom.entries if e.name == "widget")
        gadget = next(e for e in sbom.entries if e.name == "gadget")
        assert widget.version_constraint == ">=1.2.3"
        assert gadget.version_constraint == "*"


class TestDependencyEntry:
    def test_is_frozen_and_rejects_unknown_fields(self) -> None:
        entry = DependencyEntry(ecosystem="python", name="fastapi", version_constraint=">=0.115")
        with pytest.raises(Exception):
            DependencyEntry(
                ecosystem="python", name="fastapi", version_constraint=">=0.115",
                extra_field="not-allowed",  # type: ignore[call-arg]
            )
        with pytest.raises(Exception):
            entry.name = "changed"  # type: ignore[misc]
