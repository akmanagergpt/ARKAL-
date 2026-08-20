#!/usr/bin/env python3
"""Build the existing Command Center composition root as a bundled sidecar."""

from __future__ import annotations

import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "arkali-backend-x86_64-pc-windows-msvc"
OUTPUT = ROOT / "src-tauri" / "binaries"
WORK = ROOT / "src-tauri" / "target" / "pyinstaller"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        TARGET,
        "--distpath",
        str(OUTPUT),
        "--workpath",
        str(WORK / "work"),
        "--specpath",
        str(WORK),
        "--paths",
        str(ROOT / "backend"),
        "--collect-submodules",
        "arkali",
        "--add-data",
        f"{ROOT / 'backend' / 'alembic'};backend/alembic",
        "--add-data",
        f"{ROOT / 'backend' / 'alembic.ini'};backend",
        "--add-data",
        f"{ROOT / 'docs' / 'canonical'};docs/canonical",
        "--add-data",
        f"{ROOT / 'docs' / 'ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md'};docs",
        str(ROOT / "scripts" / "run_command_center.py"),
    ]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
