"""Canonical local-runtime adapter selection, shared between scripts.

Validation/composition helper, not application source code — the same
shape `handoff_architecture.py` already establishes for a plain,
`__main__`-less module living directly in `scripts/` and imported by
sibling scripts, rather than a package module inside `backend/arkali`
(`engineering.localai`'s own `test_no_sibling_module_imports_a_concrete_
adapter_directly` deliberately forbids any module there but the adapters
themselves from choosing between concrete adapter classes — this module's
whole job is exactly that choice, so it belongs here, at the composition
root, alongside `run_command_center.py`/`run_factory_worker.py`
themselves, both already documented as outside the measured architecture
graph).

ONE SELECTION RULE, TWO REAL CALLERS. `run_command_center.py` (Command
Center composition: Providers snapshot, Factory job submission, guided
intake) and `run_factory_worker.py` (the actual staged-generation
executor, a separate subprocess) must each resolve the SAME configured
local runtime the SAME way. Before this fix, only the former did; the
worker's own `model_factory` unconditionally constructed `OllamaAdapter()`
and called `.infer("qwen2.5-coder:14b", ...)` regardless of what the rest
of the system had configured (real evidence, this session:
`ARKALI_LOCAL_RUNTIME=openai_compatible` was genuinely selected and
genuinely CONFIGURED via `capability_query.compose_real_capability_
authority`, yet the worker still attempted Ollama, because it never
consulted this rule at all — `FACTORY_RUNTIME_SELECTION_WIRING_GAP`).

`ARKALI_LOCAL_RUNTIME` (default `"ollama"`) selects which already-
existing `LocalRuntimeAdapter` `local_runtime_adapter()` constructs; any
other value honestly falls back to Ollama rather than raising or guessing
a third shape — never invent a runtime nobody configured.
`ARKALI_LOCAL_RUNTIME_ENDPOINT`/`ARKALI_LOCAL_RUNTIME_REASONING_EFFORT`
are read only for the `openai_compatible` branch; Ollama has neither an
endpoint override nor a reasoning-effort concept.

`local_runtime_model_id()` is the other half of the same real problem:
whichever adapter was selected, its caller must call `.infer()` with a
real model id that actually belongs to that runtime — never a literal
that belonged to a different one. The Ollama branch's own existing
default model id is preserved unchanged here (no new network call, no
behavior change for the already-proven path). Every other runtime has no
such literal to preserve, so its model id is resolved from a real, live
`list_models()` call on the adapter itself — never a hard-coded id for
one specific server — and a real, honest error is raised when the
configured endpoint reports no models at all, rather than silently
guessing one.
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

#: Bionic's own documented default (OpenAI-compatible, just-in-time model
#: loading) — a loopback default, never a hard-coded business-logic URL:
#: `ARKALI_LOCAL_RUNTIME_ENDPOINT` overrides it, exactly like every other
#: env-driven default in this module.
_OPENAI_COMPATIBLE_DEFAULT_ENDPOINT = "http://127.0.0.1:1234"

#: The existing, long-proven Ollama default — unchanged by this module;
#: named here only so every real caller reads the identical literal
#: rather than keeping its own copy.
OLLAMA_DEFAULT_MODEL_ID = "qwen2.5-coder:14b"


def local_runtime_name() -> str:
    """The real, configured runtime name — never inferred from anything
    but this one environment variable, so every caller agrees on it."""
    return os.environ.get("ARKALI_LOCAL_RUNTIME", "ollama")


def local_runtime_adapter(
    *, json_mode: bool = False, max_output_tokens: int | None = None,
) -> LocalRuntimeAdapter:
    """The one `LocalRuntimeAdapter` every real caller composes.

    Defaults to `OllamaAdapter()`, byte-identical to every existing
    caller's own prior behavior. `ARKALI_LOCAL_RUNTIME=openai_compatible`
    selects the existing, unmodified `OpenAICompatibleAdapter` instead
    (e.g. Bionic's own local server) — ARK-REQ-0016's adapter Protocol
    already makes this a same-shape swap; no second provider framework,
    no Ollama-specific change. Real availability still comes from
    `compose_real_capability_authority`'s own real probe, never from this
    selection alone.
    """
    if local_runtime_name() == "openai_compatible":
        endpoint = os.environ.get(
            "ARKALI_LOCAL_RUNTIME_ENDPOINT", _OPENAI_COMPATIBLE_DEFAULT_ENDPOINT,
        )
        return OpenAICompatibleAdapter(
            endpoint, json_mode=json_mode, max_output_tokens=max_output_tokens,
            # Opt-in only: unset by default, so every existing caller's own
            # request shape is byte-unchanged. Real, documented, provider-
            # agnostic OpenAI field, verified live against Bionic to empty
            # a reasoning model's own hidden `reasoning_content`.
            reasoning_effort=os.environ.get("ARKALI_LOCAL_RUNTIME_REASONING_EFFORT"),
        )
    return OllamaAdapter(json_mode=json_mode, max_output_tokens=max_output_tokens)


def local_runtime_model_id(adapter: LocalRuntimeAdapter) -> str:
    """The real model id `.infer()` must be called with for `adapter`.

    The Ollama branch's own existing default is preserved unchanged — no
    new network call, no behavior change for the already-proven path.
    Any other runtime has no such literal to preserve, so it is resolved
    from a real, live `list_models()` call on `adapter` itself — never a
    hard-coded model id for one specific server.
    """
    if adapter.runtime == "ollama":
        return OLLAMA_DEFAULT_MODEL_ID
    models = adapter.list_models()
    if not models:
        raise RuntimeError(
            f"no models discovered from the configured {adapter.runtime!r} runtime"
        )
    return models[0].model_id


__all__ = [
    "OLLAMA_DEFAULT_MODEL_ID",
    "local_runtime_adapter",
    "local_runtime_model_id",
    "local_runtime_name",
]
