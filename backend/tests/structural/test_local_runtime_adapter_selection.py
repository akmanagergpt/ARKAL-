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


def test_e2_reasoning_effort_is_opt_in_and_unset_by_default(mod, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ARKALI_LOCAL_RUNTIME", "openai_compatible")
    monkeypatch.delenv("ARKALI_LOCAL_RUNTIME_REASONING_EFFORT", raising=False)
    default = mod._local_runtime_adapter()
    assert default._reasoning_effort is None

    monkeypatch.setenv("ARKALI_LOCAL_RUNTIME_REASONING_EFFORT", "none")
    configured = mod._local_runtime_adapter()
    assert configured._reasoning_effort == "none"


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


def test_g_a_plain_openai_compatible_server_with_no_native_metadata_stays_honestly_unconfigured(
    monkeypatch,
) -> None:
    """Real Command Center data-flow proof (item L), the FALLBACK case: not
    every OpenAI-compatible server is LM Studio-shaped. When `/api/v0/
    models` does not exist (mocked here as returning the same minimal
    `/v1/models` shape for every URL, so no native `quantization` is ever
    found), `evaluate_suitability` (pre-existing, deliberately conservative
    "never guess capability" gate, unmodified by this integration)
    honestly returns `NOT_TESTED` rather than `PASS` -- even though the
    generic id-suffix parse alone recovers a real `parameter_size`.
    `default_capability_id` stays `None`, exactly as it would for any
    local model this repository cannot verify fits in RAM. Availability is
    never hard-coded: swap this mock for a real, unreachable server and
    the exact same code path degrades to a real `NOT_CONFIGURED`, proven
    identically to Ollama's own behavior in `test_command_providers_api.py`."""

    def urlopen(request, timeout=None):  # noqa: ANN001
        return _ModelsResponse()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    adapter = OpenAICompatibleAdapter()
    authority = compose_real_capability_authority(REPO, adapter, "9B")

    assert adapter.probe().state.value == "PASS"
    assert authority.default_capability_id is None
    assert authority.default_model_id is None


class _NativeModelsResponse:
    status = 200

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"data": [{
            "id": "qwen/qwen3.5-9b", "quantization": "Q4_K_M",
            "max_context_length": 262144,
        }]}).encode()


def test_h_a_native_lm_studio_style_server_resolves_to_a_real_configured_model(
    monkeypatch,
) -> None:
    """The fixed case, mirroring Bionic's own real `/api/v0/models`
    response (real evidence, this session: `quantization: "Q4_K_M"`,
    `max_context_length: 262144` for `qwen/qwen3.5-9b`). With real
    quantization AND a real, generically-parsed parameter-size ("9B" from
    the id itself), `evaluate_suitability` now has what it always needed
    and genuinely resolves `PASS` -- `default_capability_id`/
    `default_model_id` become real, non-`None` values, with no fabricated
    capacity data anywhere in this path."""

    def urlopen(request, timeout=None):  # noqa: ANN001
        url = request if isinstance(request, str) else request.full_url
        if "/api/v0/models" in url:
            return _NativeModelsResponse()
        return _ModelsResponse()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    adapter = OpenAICompatibleAdapter()
    authority = compose_real_capability_authority(REPO, adapter, "9B")

    assert authority.default_capability_id == "localai.openai_compatible.qwen_qwen3_5_9b"
    assert authority.default_model_id == "qwen/qwen3.5-9b"
