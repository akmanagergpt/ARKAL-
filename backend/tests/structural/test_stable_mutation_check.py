"""Negative control for structure check 11 (defect F-0022).

Check 11 was rewritten at Phase 4. Its predecessor flagged any module that
*mentioned* `WRITE_STABLE_FILE` or `ROLLBACK_STABLE`, which was right while no
code existed and wrong the moment a phase had to implement the policy denying
those operations.

A rewritten check needs proof it still detects what it is for. These controls
plant a real mutation path and confirm it is caught, and confirm that a policy
module naming the same classes without any write capability is not. A check that
cannot reject is not evidence (F-0017); a check that rejects everything is not
useful either, so both directions are asserted.

The operation-class names come from the authority map, so this control cannot
drift onto a private list.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
VALIDATOR = REPO / "scripts" / "check_repository_structure.py"


def load_validator():
    """Import the deployed validator so the control tests the real rule."""
    spec = importlib.util.spec_from_file_location("check_structure", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator():
    return load_validator()


@pytest.fixture(scope="module")
def stable_classes(validator) -> list[str]:
    raw = yaml.safe_load(
        (REPO / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
    )
    found = validator.stable_mutation_classes(raw)
    assert found, "no stable-mutation class derived; the control would be vacuous"
    return found


def flags(validator, body: str, stable_classes: list[str]) -> bool:
    return bool(validator.is_stable_mutation_path(body, stable_classes))


class TestCheck11StillDetects:
    def test_a_real_mutation_path_is_flagged(
        self, validator, stable_classes: list[str]
    ) -> None:
        planted = (
            "def apply(target):\n"
            "    # WRITE_STABLE_FILE\n"
            "    with open(target, 'w') as handle:\n"
            "        handle.write('mutated')\n"
        )
        assert flags(validator, planted, stable_classes)

    @pytest.mark.parametrize(
        "call",
        [
            "shutil.copy(a, b)",
            "os.replace(a, b)",
            "os.remove(a)",
            "pathlib.Path(p).write_text('x')",
            "subprocess.run(['cmd'])",
        ],
    )
    def test_each_write_capable_construct_is_detected(
        self, validator, call: str, stable_classes: list[str]
    ) -> None:
        body = f"# ROLLBACK_STABLE\ndef f():\n    {call}\n"
        assert flags(validator, body, stable_classes)

    def test_a_policy_module_naming_the_classes_is_not_flagged(
        self, validator, stable_classes: list[str]
    ) -> None:
        """Phase 4's PDP names them in a deny rule and performs no write."""
        body = (
            "RULES = {'WRITE_STABLE_FILE': 'DENY', 'ROLLBACK_STABLE': 'DENY'}\n"
            "def decide(op):\n"
            "    return RULES.get(op, 'DENY')\n"
        )
        assert not flags(validator, body, stable_classes)

    def test_a_write_without_a_stable_class_is_not_flagged(
        self, validator, stable_classes: list[str]
    ) -> None:
        body = "def save(p):\n    open(p, 'w').write('ordinary workspace file')\n"
        assert not flags(validator, body, stable_classes)

    def test_an_empty_class_set_never_reports_a_clean_pass(
        self, validator
    ) -> None:
        """No derived classes means the check cannot run, not that it passed."""
        assert validator.is_stable_mutation_path("anything", []) is False
        assert validator.stable_mutation_classes(
            {"operation_classes": {}}
        ) == []


class TestCheck11IsNotVacuous:
    def test_the_derived_class_set_is_exactly_the_canonical_pair(
        self, stable_classes: list[str]
    ) -> None:
        assert stable_classes == ["ROLLBACK_STABLE", "WRITE_STABLE_FILE"]

    def test_the_validator_excludes_only_scripts_and_tests(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        assert 'f.startswith(("scripts/", "backend/tests/"))' in source

    def test_the_validator_derives_classes_from_the_authority_map(self) -> None:
        """A hard-coded list here would be the F-0013 defect."""
        source = VALIDATOR.read_text(encoding="utf-8")
        assert 'amap["operation_classes"]' in source
