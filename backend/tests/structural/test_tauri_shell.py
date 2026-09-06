"""Phase 28 desktop-shell boundaries.

These controls prove repository structure, not runtime execution. Cargo and the
real desktop journey provide the execution evidence separately.
"""

from __future__ import annotations

import json
import pathlib
import tomllib


REPO = pathlib.Path(__file__).resolve().parents[3]
TAURI = REPO / "src-tauri"


def test_tauri_two_hosts_the_existing_frontend_build() -> None:
    config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    assert config["$schema"] == "https://schema.tauri.app/config/2"
    assert config["build"]["frontendDist"] == "../frontend/dist"
    before_build = config["build"]["beforeBuildCommand"]
    assert before_build.startswith("npm run build && ")
    assert "scripts\\build_desktop_backend.py" in before_build
    assert not (TAURI / "frontend").exists()
    assert not (TAURI / "ui").exists()


def test_desktop_backend_bundles_authoritative_governance_inputs() -> None:
    build = (REPO / "scripts" / "build_desktop_backend.py").read_text(
        encoding="utf-8"
    )
    for relative in (
        "'build' / 'BUILD_STATE.md'",
        "'build' / 'OPEN_BLOCKERS.md'",
        "'acceptance' / 'HUMAN_GATE_RECORDS.md'",
    ):
        assert relative in build


def test_native_bridge_is_empty_and_fail_closed() -> None:
    source = (TAURI / "src" / "main.rs").read_text(encoding="utf-8")
    lifecycle = (TAURI / "src" / "backend_runtime.rs").read_text(encoding="utf-8")
    config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    assert "invoke_handler" not in source
    assert "#[tauri::command]" not in source
    assert config["app"]["security"]["capabilities"] == []
    for forbidden in (
        "tauri-plugin-shell",
        "tauri-plugin-fs",
        "tauri-plugin-opener",
        "cmd.exe",
        "powershell",
    ):
        assert forbidden not in source + lifecycle


def test_backend_process_is_fixed_and_not_frontend_reachable() -> None:
    source = (TAURI / "src" / "main.rs").read_text(encoding="utf-8")
    lifecycle = (TAURI / "src" / "backend_runtime.rs").read_text(encoding="utf-8")
    assert "std::process::Command" not in source
    assert "Command::new(if use_bundled { bundled } else { python })" in lifecycle
    assert 'join(".venv").join("Scripts").join("python.exe")' in lifecycle
    assert 'join("scripts").join("run_command_center.py")' in lifecycle
    assert 'resource_dir.join("arkali-backend.exe")' in lifecycle
    assert '.args(["--host", "127.0.0.1", "--port", "8000", "--db"])' in lifecycle
    assert "std::env::args" not in lifecycle
    assert "std::env::var" not in lifecycle
    assert "invoke_handler" not in source


def test_rust_manifest_has_no_native_capability_plugin() -> None:
    manifest = tomllib.loads((TAURI / "Cargo.toml").read_text(encoding="utf-8"))
    dependencies = manifest["dependencies"]
    assert set(dependencies) == {"tauri", "tauri-plugin-single-instance"}
    assert dependencies["tauri"]["features"] == []
    assert dependencies["tauri-plugin-single-instance"] == "2"


def test_desktop_network_policy_is_loopback_only() -> None:
    config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    csp = config["app"]["security"]["csp"]
    assert "connect-src 'self' http://127.0.0.1:8000" in csp
    assert "https:" not in csp
    assert "*" not in csp
