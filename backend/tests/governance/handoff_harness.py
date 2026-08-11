"""Shared loaders for the handoff-validator controls. NOT a test module.

Follows the `durable_harness.py` / `plane_harness.py` precedent: real shared
infrastructure that several test modules import and pytest collects from none of
them, because `python_files = ["test_*.py"]`.

The validator and its architecture half are loaded BY PATH rather than imported
by name, because `scripts/` is not a package and never becomes one - the same
reason `check_handoff.py` reaches its siblings through `sys.path`.
"""

from __future__ import annotations

import importlib.util
import pathlib
import types

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
VALIDATOR = SCRIPTS / "check_handoff.py"
ARCHITECTURE = SCRIPTS / "handoff_architecture.py"
HANDOFF = REPO / "ARKALI_HANDOFF.md"


def load_module(path: pathlib.Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_validator() -> types.ModuleType:
    return load_module(VALIDATOR)


def load_architecture() -> types.ModuleType:
    """The F-0047 half. Loading the validator first puts `scripts/` on the path."""
    load_validator()
    return load_module(ARCHITECTURE)


def drift_names(validator: types.ModuleType, text: str) -> list[str]:
    return list(validator.validate(REPO, text).drift)


def replace_once(text: str, old: str, new: str) -> str:
    """Rewrite one rendered claim.

    Asserts the target exists, so no control can pass by mutating nothing - the
    F-0017 vacuity shape.
    """
    assert old in text, f"expected the handoff to render {old!r}"
    return text.replace(old, new, 1)


def rendered_fan_in(architecture: dict) -> tuple[str, int]:
    """One fan-in claim exactly as the manifest renders it, derived not named."""
    text = HANDOFF.read_text(encoding="utf-8")
    for key, measured in architecture["fan_in"].items():
        short = key.split(".", 1)[1] if key.startswith("arkali.") else key
        claim = f"`{short}` fan-in is **{measured} of {architecture['fan_in_allowed']}**"
        if claim in text:
            return claim, measured
    raise AssertionError("the manifest renders no fan-in claim this control can read")
