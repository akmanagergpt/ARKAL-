"""Canonical local-runtime adapter selection shared by Command Center and Factory worker.

The composition roots must resolve the SAME runtime and the SAME real model.
Runtime selection is controlled by ARKALI_LOCAL_RUNTIME; model selection is
controlled by ARKALI_LOCAL_RUNTIME_MODEL_ID when explicitly configured, otherwise
the selected adapter's live model list is used and the first real model is
selected. No provider-specific model id is hard-coded here.
"""

from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from arkali.engineering.localai.adapter import LocalRuntimeAdapter  # noqa: E402
from arkali.engineering.localai.ollama_adapter import OllamaAdapter  # noqa: E402
from arkali.engineering.localai.openai_compatible_adapter import (  # noqa: E402
    OpenAICompatibleAdapter,
)

_OPENAI_COMPATIBLE_DEFAULT_ENDPOINT = "http://127.0.0.1:1234"


def local_runtime_name() -> str:
    """Return the explicitly configured runtime, defaulting to Ollama."""
    return os.environ.get("ARKALI_LOCAL_RUNTIME", "ollama")


def local_runtime_adapter(
    *,
    json_mode: bool = False,
    max_output_tokens: int | None = None,
    json_schema: dict[str, object] | None = None,
) -> LocalRuntimeAdapter:
    """Construct the one real adapter shared by all composition roots."""
    if local_runtime_name() == "openai_compatible":
        endpoint = os.environ.get(
            "ARKALI_LOCAL_RUNTIME_ENDPOINT", _OPENAI_COMPATIBLE_DEFAULT_ENDPOINT,
        )
        return OpenAICompatibleAdapter(
            endpoint,
            json_mode=json_mode,
            max_output_tokens=max_output_tokens,
            reasoning_effort=os.environ.get("ARKALI_LOCAL_RUNTIME_REASONING_EFFORT"),
            json_schema=json_schema,
        )
    return OllamaAdapter(
        json_mode=json_mode,
        max_output_tokens=max_output_tokens,
        json_schema=json_schema,
    )


def local_runtime_model_id(adapter: LocalRuntimeAdapter) -> str:
    """Resolve a real model id belonging to the selected runtime.

    An explicit ARKALI_LOCAL_RUNTIME_MODEL_ID is honored only when the selected
    runtime actually reports that model. Without an override, the first model
    returned by the live adapter discovery is selected. This keeps Command
    Center capability exposure and the Factory worker on the same real model
    instead of silently falling back to a stale provider-specific literal.
    """
    requested = os.environ.get("ARKALI_LOCAL_RUNTIME_MODEL_ID", "").strip()
    models = adapter.list_models()
    if requested:
        if any(model.model_id == requested for model in models):
            return requested
        raise RuntimeError(
            f"configured model {requested!r} is not available from the "
            f"{adapter.runtime!r} runtime"
        )
    if not models:
        raise RuntimeError(
            f"no models discovered from the configured {adapter.runtime!r} runtime"
        )
    return models[0].model_id


__all__ = [
    "local_runtime_adapter",
    "local_runtime_model_id",
    "local_runtime_name",
]
