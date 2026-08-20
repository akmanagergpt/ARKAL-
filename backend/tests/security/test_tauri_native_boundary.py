"""Adversarial controls for the Phase 28 native boundary."""

from __future__ import annotations

import json
import pathlib
import re


REPO = pathlib.Path(__file__).resolve().parents[3]
TAURI = REPO / "src-tauri"
RUST = "\n".join(
    path.read_text(encoding="utf-8") for path in (TAURI / "src").glob("*.rs")
)


def test_frontend_has_no_native_command_or_permission() -> None:
    config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    assert config["app"]["security"]["capabilities"] == []
    assert "invoke_handler" not in RUST
    assert "#[tauri::command]" not in RUST


def test_no_shell_filesystem_opener_or_credential_plugin_exists() -> None:
    manifests = (
        (TAURI / "Cargo.toml").read_text(encoding="utf-8")
        + (REPO / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    for forbidden in ("plugin-shell", "plugin-fs", "plugin-opener", "plugin-store"):
        assert forbidden not in manifests


def test_the_only_process_target_is_the_canonical_python_runtime() -> None:
    commands = re.findall(r"Command::new\(([^)]+)\)", RUST)
    assert commands == ["python"]
    assert 'join(".venv").join("Scripts").join("python.exe")' in RUST
    assert "std::env::args" not in RUST
    assert "std::env::var" not in RUST


def test_network_and_cors_boundaries_name_only_fixed_loopback_origins() -> None:
    config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    csp = config["app"]["security"]["csp"]
    assert "http://127.0.0.1:8000" in csp
    assert "https:" not in csp and "*" not in csp
    backend = (REPO / "backend/arkali/surfaces/command/app.py").read_text(encoding="utf-8")
    assert 'allow_origins=["http://tauri.localhost"]' in backend

