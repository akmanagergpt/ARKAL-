#!/usr/bin/env python3
"""Build and freeze the canonical Phase 29 Windows installer artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src-tauri" / "tauri.conf.json"
BUNDLE_DIR = ROOT / "src-tauri" / "target" / "release" / "bundle" / "nsis"
OUTPUT_DIR = ROOT / "artifacts" / "installer"
OUTPUT = OUTPUT_DIR / "ARKALI_Setup.exe"
PROVENANCE = OUTPUT_DIR / "ARKALI_Setup.provenance.json"


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _build() -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise FileNotFoundError("official Node npm executable is unavailable")
    subprocess.run(
        [npm, "run", "tauri", "--", "build"],
        cwd=ROOT / "frontend",
        check=True,
    )


def freeze(*, build: bool) -> dict[str, object]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    version = config["version"]
    product = config["productName"]
    source = BUNDLE_DIR / f"{product}_{version}_x64-setup.exe"
    if build:
        _build()
    if not source.is_file():
        raise FileNotFoundError(f"Tauri NSIS output is absent: {source}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, OUTPUT)
    record: dict[str, object] = {
        "schema": "ARKALI-INSTALLER-PROVENANCE-V1",
        "artifact": OUTPUT.name,
        "product": product,
        "version": version,
        "identifier": config["identifier"],
        "format": "NSIS",
        "architecture": "x86_64-pc-windows-msvc",
        "install_mode": config["bundle"]["windows"]["nsis"]["installMode"],
        "source_commit": _git_head(),
        "sha256": _sha256(OUTPUT),
        "size_bytes": OUTPUT.stat().st_size,
    }
    PROVENANCE.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="freeze an already-built Tauri NSIS output",
    )
    args = parser.parse_args(argv[1:])
    print(json.dumps(freeze(build=not args.no_build), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
