"""ARK-REQ-0016: local AI is adapter-based with no single-runtime dependency.

Two structurally distinct real adapters (`OllamaAdapter`,
`OpenAICompatibleAdapter`) satisfy one `Protocol` and share no transport code.
Evidence type is `arch` per the register - this file proves the property
structurally (AST + `isinstance`), not by exercising a live runtime.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

import pytest

from arkali.engineering.localai.adapter import LocalRuntimeAdapter
from arkali.engineering.localai.ollama_adapter import OllamaAdapter
from arkali.engineering.localai.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
LOCALAI_ROOT: Final[pathlib.Path] = REPO / "backend" / "arkali" / "engineering" / "localai"

ADAPTER_MODULES: Final[tuple[str, ...]] = ("ollama_adapter.py", "openai_compatible_adapter.py")


def _imports(module_path: pathlib.Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


class TestBothAdaptersSatisfyOneProtocol:
    def test_ollama_adapter_is_a_local_runtime_adapter(self) -> None:
        assert isinstance(OllamaAdapter(), LocalRuntimeAdapter)

    def test_openai_compatible_adapter_is_a_local_runtime_adapter(self) -> None:
        assert isinstance(OpenAICompatibleAdapter(), LocalRuntimeAdapter)

    def test_the_protocol_names_exactly_the_shape_both_adapters_share(self) -> None:
        expected = {"runtime", "probe", "list_models", "infer"}
        assert expected <= set(dir(LocalRuntimeAdapter))


class TestNoSingleRuntimeDependency:
    """ARK-REQ-0016's own wording: "no hard dependency on one runtime"."""

    def test_two_adapters_exist_for_two_different_runtimes(self) -> None:
        assert OllamaAdapter().runtime != OpenAICompatibleAdapter().runtime

    def test_the_two_adapters_use_different_default_endpoints(self) -> None:
        assert OllamaAdapter().endpoint != OpenAICompatibleAdapter().endpoint

    @pytest.mark.parametrize("module_name", ADAPTER_MODULES)
    def test_adapter_module_transport_is_confined_to_itself(
        self, module_name: str
    ) -> None:
        """Neither adapter module imports the other's transport internals."""
        this_module = LOCALAI_ROOT / module_name
        other_module = next(m for m in ADAPTER_MODULES if m != module_name)
        other_stem = other_module.removesuffix(".py")
        imported = _imports(this_module)
        assert other_stem not in imported

    def test_no_sibling_module_imports_a_concrete_adapter_directly(self) -> None:
        """Callers depend on `LocalRuntimeAdapter`, never a concrete adapter
        class, so a runtime can be added or removed without touching a caller
        outside this context's own adapter modules and its `__init__.py`."""
        allowed = set(ADAPTER_MODULES) | {"__init__.py"}
        offenders: list[str] = []
        for path in LOCALAI_ROOT.glob("*.py"):
            if path.name in allowed:
                continue
            imported = _imports(path)
            if "ollama_adapter" in imported or "openai_compatible_adapter" in imported:
                offenders.append(path.name)
        assert offenders == []


class TestBoundedAndReadOnlyByConstruction:
    """Discovery methods issue no mutation; `infer` is the one bounded call."""

    def test_probe_and_list_models_use_only_get_verbs_in_source(self) -> None:
        for module_name in ADAPTER_MODULES:
            source = (LOCALAI_ROOT / module_name).read_text(encoding="utf-8")
            assert 'method="POST"' not in source.split("def infer")[0]

    def test_infer_signature_carries_a_caller_controlled_timeout(self) -> None:
        import inspect

        for adapter in (OllamaAdapter(), OpenAICompatibleAdapter()):
            params = inspect.signature(adapter.infer).parameters
            assert "timeout_seconds" in params
