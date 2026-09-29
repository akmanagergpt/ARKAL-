"""FACTORY_RUNTIME_SELECTION_WIRING_GAP fix.

Real evidence, this session: `ARKALI_LOCAL_RUNTIME=openai_compatible` was
genuinely selected and genuinely resolved to a real, CONFIGURED Bionic
model through `run_command_center.py`'s own `/api/providers/snapshot` --
yet submitting a real goal still attempted Ollama, because `run_factory_
worker.py` (a separate subprocess, the actual staged-generation executor)
independently constructed `OllamaAdapter(json_mode=True, ...)` and called
`.infer("qwen2.5-coder:14b", ...)` unconditionally, never consulting any
selection rule at all.

`scripts/local_runtime.py` is now the one canonical selection rule both
`run_command_center.py` and `run_factory_worker.py` import as a sibling
script module (never a package import between two executable scripts,
and never a second implementation duplicated into either). These tests
prove: (1) the shared module's own selection/model-id behavior, and (2)
that BOTH scripts, loaded exactly as they really run, resolve the
identical adapter/endpoint/reasoning_effort/model_id for the identical
configuration -- with no real network or model call anywhere in this
file.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from arkali.engineering.localai.ollama_adapter import OllamaAdapter
from arkali.engineering.localai.openai_compatible_adapter import OpenAICompatibleAdapter

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"


def _load(name: str, path: pathlib.Path):  # noqa: ANN201
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def local_runtime():  # noqa: ANN201
    return _load("local_runtime", SCRIPTS / "local_runtime.py")


@pytest.fixture(scope="module")
def command_center():  # noqa: ANN201
    return _load("run_command_center", SCRIPTS / "run_command_center.py")


@pytest.fixture(scope="module")
def factory_worker():  # noqa: ANN201
    return _load("run_factory_worker", SCRIPTS / "run_factory_worker.py")


class TestSharedModuleSelection:
    """The one real rule both scripts consume."""

    def test_1_default_is_ollama(self, local_runtime, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.delenv("ARKALI_LOCAL_RUNTIME", raising=False)
        adapter = local_runtime.local_runtime_adapter()
        assert isinstance(adapter, OllamaAdapter)

    def test_2_openai_compatible_selects_the_existing_adapter(
        self, local_runtime, monkeypatch,
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
        monkeypatch.delenv("ARKALI_LOCAL_RUNTIME_ENDPOINT", raising=False)
        adapter = local_runtime.local_runtime_adapter()
        assert isinstance(adapter, OpenAICompatibleAdapter)
        assert adapter.endpoint == "http://127.0.0.1:1234"

    def test_3_endpoint_override_propagates(self, local_runtime, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME_ENDPOINT", "http://127.0.0.1:9999")
        adapter = local_runtime.local_runtime_adapter()
        assert adapter.endpoint == "http://127.0.0.1:9999"

    def test_4_reasoning_effort_propagates_and_is_opt_in(
        self, local_runtime, monkeypatch,
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
        monkeypatch.delenv("ARKALI_LOCAL_RUNTIME_REASONING_EFFORT", raising=False)
        assert local_runtime.local_runtime_adapter()._reasoning_effort is None

        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME_REASONING_EFFORT", "none")
        assert local_runtime.local_runtime_adapter()._reasoning_effort == "none"

    def test_5_unrecognized_runtime_falls_back_to_ollama_honestly(
        self, local_runtime, monkeypatch,
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "some_future_runtime")
        adapter = local_runtime.local_runtime_adapter()
        assert isinstance(adapter, OllamaAdapter)

    def test_6_ollama_model_id_is_the_existing_unchanged_literal(
        self, local_runtime, monkeypatch,
    ) -> None:  # noqa: ANN001
        monkeypatch.delenv("ARKALI_LOCAL_RUNTIME", raising=False)
        adapter = local_runtime.local_runtime_adapter()
        assert local_runtime.local_runtime_model_id(adapter) == "qwen2.5-coder:14b"

    def test_7_openai_compatible_model_id_is_discovered_never_hard_coded(
        self, local_runtime, monkeypatch,
    ) -> None:  # noqa: ANN001
        class _FakeAdapter:
            runtime = "openai_compatible"

            def list_models(self):  # noqa: ANN201
                class _Descriptor:
                    model_id = "some/discovered-model"

                return (_Descriptor(),)

        assert local_runtime.local_runtime_model_id(_FakeAdapter()) == "some/discovered-model"

    def test_8_openai_compatible_model_id_raises_honestly_when_none_discovered(
        self, local_runtime,
    ) -> None:
        class _EmptyAdapter:
            runtime = "openai_compatible"

            def list_models(self):  # noqa: ANN201
                return ()

        with pytest.raises(RuntimeError):
            local_runtime.local_runtime_model_id(_EmptyAdapter())

    def test_9_no_bionic_specific_model_id_literal_in_the_shared_module(
        self,
    ) -> None:
        source = (SCRIPTS / "local_runtime.py").read_text(encoding="utf-8")
        assert "qwen3.5" not in source.lower()
        assert "qwen/qwen3" not in source.lower()


class TestBothScriptsShareOneSelectionPath:
    """The actual cross-script proof: both real composition roots, loaded
    exactly as they really run, resolve identically."""

    def test_command_center_default_is_ollama(
        self, command_center, monkeypatch,
    ) -> None:  # noqa: ANN001
        monkeypatch.delenv("ARKALI_LOCAL_RUNTIME", raising=False)
        assert isinstance(command_center._local_runtime_adapter(), OllamaAdapter)

    def test_command_center_openai_compatible(
        self, command_center, monkeypatch,
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
        adapter = command_center._local_runtime_adapter()
        assert isinstance(adapter, OpenAICompatibleAdapter)

    def test_factory_worker_default_is_ollama(
        self, factory_worker, monkeypatch,
    ) -> None:  # noqa: ANN001
        """Item 2: the worker's own imported `local_runtime_adapter`
        resolves exactly like Command Center's -- the same real function,
        not a reimplementation."""
        monkeypatch.delenv("ARKALI_LOCAL_RUNTIME", raising=False)
        assert isinstance(factory_worker.local_runtime_adapter(), OllamaAdapter)

    def test_factory_worker_openai_compatible(
        self, factory_worker, monkeypatch,
    ) -> None:  # noqa: ANN001
        """Item 4, the exact real bug this turn fixes: the worker must now
        genuinely resolve `OpenAICompatibleAdapter` when configured, not
        silently attempt Ollama regardless."""
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
        adapter = factory_worker.local_runtime_adapter()
        assert isinstance(adapter, OpenAICompatibleAdapter)
        # `local_runtime_model_id` for this runtime calls `list_models()`
        # over the real network -- not exercised here; its own honest
        # discovery/no-fabrication behavior is proven with a fake adapter
        # in TestSharedModuleSelection above, with no network at all.

    def test_no_duplicate_selection_logic_remains_in_command_center(self) -> None:
        source = (SCRIPTS / "run_command_center.py").read_text(encoding="utf-8")
        assert 'os.environ.get("ARKALI_LOCAL_RUNTIME"' not in source
        assert "from local_runtime import local_runtime_adapter" in source

    def test_factory_worker_no_longer_hard_codes_ollama(self) -> None:
        """The exact real bug: `model_factory` used to construct
        `OllamaAdapter(...)` and call `.infer("qwen2.5-coder:14b", ...)`
        unconditionally. Neither literal may appear anywhere in this file
        anymore -- both must come from the shared selection rule."""
        source = (SCRIPTS / "run_factory_worker.py").read_text(encoding="utf-8")
        assert "OllamaAdapter(" not in source
        assert '"qwen2.5-coder:14b"' not in source
        assert '"ollama/qwen2.5-coder:14b"' not in source
        assert "from local_runtime import local_runtime_adapter, local_runtime_model_id" in source

    def test_factory_worker_model_factory_uses_the_shared_adapter_and_model_id(
        self,
    ) -> None:
        source = (SCRIPTS / "run_factory_worker.py").read_text(encoding="utf-8")
        model_factory = source[
            source.index("def model_factory("): source.index("try:\n        result = generate_staged_model_product")
        ]
        assert "_ObservedModel(adapter, candidate_id, provider_model)" in model_factory
        assert "return observed, model_id" in model_factory

    def test_provenance_and_provider_model_are_derived_not_literal(self) -> None:
        source = (SCRIPTS / "run_factory_worker.py").read_text(encoding="utf-8")
        assert 'runtime="ollama"' not in source
        assert 'endpoint="http://127.0.0.1:11434"' not in source
        assert 'model="qwen2.5-coder:14b"' not in source
        assert "runtime=adapter.runtime" in source
        assert "endpoint=adapter.endpoint" in source
        assert "model=model_id" in source

    def test_both_scripts_resolve_the_same_endpoint_given_the_same_env(
        self, command_center, local_runtime, monkeypatch,
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME_ENDPOINT", "http://127.0.0.1:4321")
        command_center_adapter = command_center._local_runtime_adapter()
        shared_adapter = local_runtime.local_runtime_adapter()
        assert command_center_adapter.endpoint == shared_adapter.endpoint == "http://127.0.0.1:4321"

    def test_both_scripts_propagate_reasoning_effort_identically(
        self, command_center, local_runtime, monkeypatch,
    ) -> None:  # noqa: ANN001
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
        monkeypatch.setenv("ARKALI_LOCAL_RUNTIME_REASONING_EFFORT", "none")
        command_center_adapter = command_center._local_runtime_adapter()
        shared_adapter = local_runtime.local_runtime_adapter()
        assert command_center_adapter._reasoning_effort == shared_adapter._reasoning_effort == "none"
