"""Phase 29 canonical installer identity and provenance controls."""

from __future__ import annotations

import ast
import json
import pathlib


REPO = pathlib.Path(__file__).resolve().parents[3]
CONFIG = json.loads((REPO / "src-tauri/tauri.conf.json").read_text("utf-8"))
BUILDER = REPO / "scripts/build_windows_installer.py"


def test_windows_installer_is_nsis_and_current_user_scoped() -> None:
    bundle = CONFIG["bundle"]
    assert bundle["targets"] == ["nsis"]
    assert bundle["windows"]["nsis"]["installMode"] == "currentUser"
    assert CONFIG["identifier"] == "dev.arkali.command-center"


def test_canonical_artifact_name_is_fixed() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    assert 'OUTPUT = OUTPUT_DIR / "ARKALI_Setup.exe"' in source
    assert 'PROVENANCE = OUTPUT_DIR / "ARKALI_Setup.provenance.json"' in source
    assert "ARKALI-INSTALLER-PROVENANCE-V1" in source


def test_builder_has_no_shell_or_external_delivery_surface() -> None:
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    for call in calls:
        for keyword in call.keywords:
            assert not (keyword.arg == "shell" and isinstance(keyword.value, ast.Constant))
    source = BUILDER.read_text(encoding="utf-8")
    assert "http://" not in source and "https://" not in source
    assert "requests" not in source and "urllib" not in source
