"""BIONIC_QWEN35_ARKALI_INTEGRATION: `scripts/run_command_center.py` hard-
coded `OllamaAdapter()` at every composition site (`_providers_wiring`,
`_factory_submitter`, `_factory_guide`) -- no local runtime was ever
selectable, so adding a second local runtime (Bionic's OpenAI-compatible
server) meant editing three call sites by hand. `_local_runtime_adapter`
is the one narrow seam this proves: `ARKALI_LOCAL_RUNTIME` selects which
already-existing `LocalRuntimeAdapter` is composed, defaulting to
byte-identical `OllamaAdapter()` construction when unset -- no second
provider framework, no change to `compose_real_capability_authority`, no
change to either adapter's own transport.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import urllib.request

import pytest

from arkali.engineering.localai.capability_query import compose_real_capability_authority
from arkali.engineering.localai.ollama_adapter import OllamaAdapter
from arkali.engineering.localai.openai_compatible_adapter import OpenAICompatibleAdapter

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "run_command_center.py"


def _module():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("run_command_center", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():  # noqa: ANN201
    return _module()


def test_a_unset_env_defaults_to_ollama_unchanged(mod, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("ARKALI_LOCAL_RUNTIME", raising=False)
    adapter = mod._local_runtime_adapter()
    assert isinstance(adapter, OllamaAdapter)
    assert adapter.endpoint == OllamaAdapter().endpoint


def test_b_explicit_ollama_env_is_the_same_default(mod, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "ollama")
    adapter = mod._local_runtime_adapter()
    assert isinstance(adapter, OllamaAdapter)


def test_c_openai_compatible_env_selects_the_existing_adapter(mod, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
    monkeypatch.delenv("ARKALI_LOCAL_RUNTIME_ENDPOINT", raising=False)
    adapter = mod._local_runtime_adapter()
    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter.endpoint == "http://127.0.0.1:1234"


def test_d_endpoint_override_is_never_hard_coded(mod, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
    monkeypatch.setenv("ARKALI_LOCAL_RUNTIME_ENDPOINT", "http://127.0.0.1:9999")
    adapter = mod._local_runtime_adapter()
    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter.endpoint == "http://127.0.0.1:9999"


def test_e_json_mode_and_token_bound_forward_to_either_adapter(mod, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("ARKALI_LOCAL_RUNTIME", raising=False)
    ollama = mod._local_runtime_adapter(json_mode=True, max_output_tokens=1200)
    assert isinstance(ollama, OllamaAdapter)

    monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
    bionic = mod._local_runtime_adapter(json_mode=True, max_output_tokens=1200)
    assert isinstance(bionic, OpenAICompatibleAdapter)
    assert bionic._json_mode is True
    assert bionic._max_output_tokens == 1200


def test_f_an_unrecognized_runtime_value_honestly_falls_back_to_ollama(
    mod, monkeypatch,
) -> None:  # noqa: ANN001
    """Never silently constructs an adapter for a runtime name nobody
    configured -- an unrecognized value falls back to the one runtime this
    host is already known to run, rather than raising or guessing a third
    shape."""
    monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "some_future_runtime")
    adapter = mod._local_runtime_adapter()
    assert isinstance(adapter, OllamaAdapter)


class _ModelsResponse:
    status = 200

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"data": [{"id": "qwen/qwen3.5-9b"}]}).encode()


def test_g_a_reachable_bionic_server_is_probed_but_not_yet_configured(
    monkeypatch,
) -> None:
    """Real Command Center data-flow proof (item L): `compose_real_
    capability_authority` genuinely probes a real, reachable OpenAI-
    compatible server (mocked here, real when Bionic is actually running)
    and genuinely discovers the real model -- but `/v1/models` carries no
    parameter-size/quantization metadata, so `evaluate_suitability` (a
    pre-existing, deliberately conservative "never guess capability" gate,
    unmodified by this integration) honestly returns `NOT_TESTED` rather
    than `PASS`. `default_capability_id` therefore stays `None`, exactly
    as it would for any local model this repository cannot verify fits in
    RAM -- this is the honest existing behavior, not a new regression, and
    not something this integration works around by fabricating capacity
    data. Availability is never hard-coded: swap this mock for a real,
    unreachable Bionic server and the exact same code path degrades to a
    real `NOT_CONFIGURED`, proven identically to Ollama's own behavior in
    `test_command_providers_api.py`."""

    def urlopen(request, timeout=None):  # noqa: ANN001
        return _ModelsResponse()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    adapter = OpenAICompatibleAdapter()
    authority = compose_real_capability_authority(REPO, adapter, "9B")

    assert adapter.probe().state.value == "PASS"
    assert authority.default_capability_id is None
    assert authority.default_model_id is None
