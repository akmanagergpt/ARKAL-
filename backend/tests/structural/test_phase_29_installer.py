"""Phase 29 canonical installer identity and provenance controls."""

from __future__ import annotations

import ast
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
CONFIG = json.loads((REPO / "src-tauri/tauri.conf.json").read_text("utf-8"))
BUILDER = REPO / "scripts/build_windows_installer.py"
RECOVERY_RUNNER = REPO / "scripts/run_phase29_recovery_journey.py"
UPGRADE_CONFIG = REPO / "src-tauri/tauri.upgrade-test.conf.json"


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


def test_upgrade_candidate_overlay_changes_version_only() -> None:
    overlay = json.loads(UPGRADE_CONFIG.read_text(encoding="utf-8"))
    assert overlay == {"version": "0.1.1"}
    assert overlay["version"] > CONFIG["version"]


def test_recovery_runner_is_fixed_to_ignored_acceptance_locations() -> None:
    source = RECOVERY_RUNNER.read_text(encoding="utf-8")
    assert 'ROOT / "artifacts" / "phase29-real-install"' in source
    assert 'ROOT / "artifacts" / "phase29-recovery"' in source
    assert "recover_failed_installer_upgrade(" in source
    assert "installers[record.to_revision_id]" in source
    assert "shell=True" not in source
    assert "APPDATA" not in source and "LOCALAPPDATA" not in source
    assert "rmtree(" not in source
