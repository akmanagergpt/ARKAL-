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
    assert "npm --prefix ../frontend run build" in config["build"]["beforeBuildCommand"]
    assert not (TAURI / "frontend").exists()
    assert not (TAURI / "ui").exists()


def test_native_bridge_is_empty_and_fail_closed() -> None:
    source = (TAURI / "src" / "main.rs").read_text(encoding="utf-8")
    config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    assert "invoke_handler" not in source
    assert "#[tauri::command]" not in source
    assert config["app"]["security"]["capabilities"] == []
    for forbidden in (
        "tauri-plugin-shell",
        "tauri-plugin-fs",
        "tauri-plugin-opener",
        "std::process::Command",
        "cmd.exe",
        "powershell",
    ):
        assert forbidden not in source


def test_rust_manifest_has_no_native_capability_plugin() -> None:
    manifest = tomllib.loads((TAURI / "Cargo.toml").read_text(encoding="utf-8"))
    dependencies = manifest["dependencies"]
    assert set(dependencies) == {"tauri"}
    assert dependencies["tauri"]["features"] == []


def test_desktop_network_policy_is_loopback_only() -> None:
    config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    csp = config["app"]["security"]["csp"]
    assert "connect-src 'self' http://127.0.0.1:8000" in csp
    assert "https:" not in csp
    assert "*" not in csp

