"""C-34 Computer-Use adversarial/negative proofs (ARK-REQ-0170, Phase 25
Package 4). Consolidates the attack classes those earlier packages did not
yet cover on their own, the identical shape
`tests/lifecycle/test_child_product_adversarial.py` already established.

Attack class -> where it is proven, unless noted:
  no direct Stable mutation
    -> TestNoDirectStableOrLiveMutationAnywhereInComputerUse
  no shadow execution path bypassing the PDP
    -> TestNoModuleExecutesWithoutGoingThroughTheRealPdp
  ASK_USER is never silently treated as permission
    -> TestAskUserIsNeverConflatedWithAuto
  a crafted facts dict cannot force AUTO on a never-AUTO class
    -> TestFactsCannotOverrideAFixedRule
  no second policy authority exists anywhere in this package
    -> TestNoShadowAuthority
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.surfaces.operations import (
    browser_boundary,
    computer_use,
    file_boundary,
    process_boundary,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
OPERATIONS_ROOT = REPO / "backend" / "arkali" / "surfaces" / "operations"

NEVER_AUTO_CLASSES = ("WRITE_STABLE_FILE", "ROLLBACK_STABLE",
                      "INSTALL_SYSTEM_SOFTWARE", "CHANGE_SYSTEM_CONFIGURATION")


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


def _source_files() -> list[pathlib.Path]:
    return sorted(p for p in OPERATIONS_ROOT.glob("*.py") if p.name != "__init__.py")


class TestNoDirectStableOrLiveMutationAnywhereInComputerUse:
    def test_no_operations_module_imports_lifecycle_release_or_recovery(self) -> None:
        offenders = []
        for path in _source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and (
                    node.module.startswith("arkali.lifecycle.release")
                    or node.module.startswith("arkali.lifecycle.recovery")
                ):
                    offenders.append((path.name, node.module))
        assert not offenders, f"surfaces.operations reaches Stable/rollback: {offenders}"

    def test_no_module_names_stable_revision_pointers_own_mutating_methods(self) -> None:
        forbidden = {"promote", "rollback_to"}
        offenders = []
        for path in _source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in forbidden:
                    offenders.append((path.name, node.attr))
        assert not offenders, f"surfaces.operations names a Stable-mutation method: {offenders}"

    def test_write_stable_file_and_rollback_stable_are_always_deny_for_this_actor(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        for operation_class in ("WRITE_STABLE_FILE", "ROLLBACK_STABLE"):
            for tier in ("TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"):
                decision = computer_use.authorize_computer_use_action(
                    pdp, operation_class=operation_class, trust_tier=tier,
                    facts={"within_preauthorized_scope": True, "lockfile_bound": True},
                )
                assert decision.decision == "DENY", (operation_class, tier)


class TestNoModuleExecutesWithoutGoingThroughTheRealPdp:
    """Every real execution primitive (subprocess.run/Popen) lives inside
    process_boundary.py alone - proving no second, ungated execution path
    exists anywhere in this package."""

    #: `hardware_telemetry.py` calls `subprocess.run` too, but only for the
    #: real, read-only `nvidia-smi` diagnostic probe Package 1 already
    #: composed unguarded from `engineering.localai.host_probe.
    #: probe_accelerator`'s own identical, pre-existing, PDP-exempt pattern -
    #: a read-only hardware query is not a Computer-Use `RUN_PROCESS`
    #: action. This exclusion is named, not silent: a THIRD module calling
    #: `subprocess.*` would still fail this control.
    _READ_ONLY_DIAGNOSTIC_PROBES = frozenset({"hardware_telemetry.py"})

    def test_only_process_boundary_calls_subprocess_run_or_popen(self) -> None:
        offenders = []
        for path in _source_files():
            if path.name in {"process_boundary.py", *self._READ_ONLY_DIAGNOSTIC_PROBES}:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr in ("run", "Popen", "call", "check_call", "check_output"):
                    receiver = ast.unparse(node.func.value).lower()
                    if "subprocess" in receiver or "os" in receiver:
                        offenders.append((path.name, node.func.attr))
        assert not offenders, f"execution outside process_boundary.py: {offenders}"

    def test_the_excluded_diagnostic_probe_is_genuinely_read_only(self) -> None:
        """The exclusion above is verified, not merely asserted: every
        `subprocess.run` call in `hardware_telemetry.py` must pass an
        `nvidia-smi --query-*` argument list and nothing that looks like a
        mutation."""
        path = OPERATIONS_ROOT / "hardware_telemetry.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
        ]
        assert calls, "hardware_telemetry.py no longer calls subprocess.run at all"
        assert '"nvidia-smi"' in path.read_text(encoding="utf-8")
        for call in calls:
            rendered = ast.unparse(call)
            assert "--query-gpu" in rendered
            assert not any(bad in rendered for bad in ("--gpu-reset", "install", "rm "))

    def test_every_execution_function_calls_authorize_computer_use_action_first(self) -> None:
        """AST proof: `execute_process`/`terminate_own_process`/
        `read_workspace_file`/`write_workspace_file`/
        `authorize_browser_navigation` each reference
        `authorize_computer_use_action` in their own body."""
        modules = {
            "process_boundary.py": ("execute_process", "terminate_own_process"),
            "file_boundary.py": ("read_workspace_file", "write_workspace_file"),
            "browser_boundary.py": ("authorize_browser_navigation",),
        }
        for filename, function_names in modules.items():
            path = OPERATIONS_ROOT / filename
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            functions = {
                node.name: node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name in function_names
            }
            for name in function_names:
                assert name in functions, f"{filename} no longer defines {name}"
                body_source = ast.unparse(functions[name])
                assert "authorize_computer_use_action" in body_source, (
                    f"{filename}::{name} does not call authorize_computer_use_action"
                )


class TestAskUserIsNeverConflatedWithAuto:
    def test_permits_execution_is_false_for_ask_user(self, pdp: PolicyDecisionPoint) -> None:
        decision = computer_use.authorize_computer_use_action(
            pdp, operation_class="BROWSER_EXTERNAL", trust_tier="TRUST-1",
        )
        assert decision.decision == "ASK_USER"
        assert decision.permits_execution is False

    def test_execute_process_does_not_run_on_ask_user(self, pdp: PolicyDecisionPoint) -> None:
        import sys

        outcome = process_boundary.execute_process(
            pdp, command=(sys.executable, "-c", "print('should not run')"),
            operation_class="BROWSER_EXTERNAL", trust_tier="TRUST-1",
        )
        assert outcome.decision.decision == "ASK_USER"
        assert outcome.executed is False


class TestFactsCannotOverrideAFixedRule:
    @pytest.mark.parametrize("operation_class", NEVER_AUTO_CLASSES)
    def test_every_true_fact_combination_still_never_resolves_auto(
        self, pdp: PolicyDecisionPoint, operation_class: str,
    ) -> None:
        adversarial_facts = {
            "target_is_loopback": True, "target_is_own_process": True,
            "within_preauthorized_scope": True, "lockfile_bound": True,
        }
        for tier in ("TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"):
            decision = computer_use.authorize_computer_use_action(
                pdp, operation_class=operation_class, trust_tier=tier,
                facts=adversarial_facts, local_only=False,
            )
            assert decision.decision != "AUTO", (operation_class, tier)


class TestNoShadowAuthority:
    def test_only_one_actor_label_is_declared_for_computer_use(self) -> None:
        assert computer_use.ACTOR == "computer_use_worker"

    def test_no_operations_module_defines_its_own_operation_class_table(self) -> None:
        """The fourteen classes are parsed from AUTHORITY_MAP.yaml by
        control.policy.operation_class alone - no dict literal here may
        shadow it."""
        offenders = []
        for path in _source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict) and len(node.keys) >= 8:
                    keys = {
                        k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
                    if "WRITE_STABLE_FILE" in keys and "RUN_PROCESS" in keys:
                        offenders.append(path.name)
        assert not offenders, f"a shadow operation-class table exists: {offenders}"
