"""Local AI adapter architecture (ARK-REQ-0016).

Owner: engineering.localai.

ADAPTER-BASED, NO SINGLE-RUNTIME DEPENDENCY. MS §Frozen technology direction:
"Local AI: adapter-based; no hard dependency on one runtime." This module
declares the one shape every local runtime adapter must satisfy
(`LocalRuntimeAdapter`, a structural `Protocol`) and the value objects that
shape trades in. Nothing here imports a concrete runtime's transport - not
`urllib`, not a vendor SDK, not a port number. A caller depends on this
Protocol, never on `OllamaAdapter` or any other concrete class; swapping or
adding a runtime therefore never touches a caller
(`backend/tests/structural/test_localai_adapter_confinement.py` proves this
directly by AST rather than by naming).

EVERY PROBE AND CALL IS READ-ONLY OR BOUNDED. `probe()` and `list_models()`
never mutate host or runtime state. `infer()` performs one bounded, timed-out
call and returns a truthful, honest outcome - never a fabricated success. This
mirrors `control.isolation.backend_probe`'s own guarantee for the same reason:
a probe or a capability query that could make itself pass is the false-success
defect the canonical set forbids.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from arkali.kernel.contracts.honest_state import HonestState

#: Re-exported so sibling adapter modules import `HonestState` from this
#: context's own boundary module rather than adding a second direct edge into
#: `kernel.contracts` - the same one-importer-per-context shape
#: `engineering.plugin.content_ref` established for `content_address`.


class LocalModelDescriptor(BaseModel):
    """One model a local runtime reports it can serve. A reference, not a copy:
    every field is read from the runtime at query time, never cached here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime: str
    model_id: str
    parameter_size: str = ""
    quantization: str = ""
    context_length: int = 0
    endpoint: str = ""
    capabilities: tuple[str, ...] = ()


class RuntimeProbeResult(BaseModel):
    """Deterministic, honest answer to "is this runtime reachable?"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime: str
    state: HonestState
    detail: str
    endpoint: str = ""


class CompletionMetadata(BaseModel):
    """Bounded, provider-reported facts about how one real inference call
    ended - a completion FACT the runtime itself reported, never a retry
    or budget DECISION ARKALI made about it (F-0100's own observability-
    before-behavior boundary: this phase records truth, it does not act
    on it). Generic across runtimes: field names name no one provider's
    own vocabulary (never `done`/`done_reason`, Ollama's own names), so a
    future adapter reporting the same kind of fact under different keys
    (e.g. an OpenAI-compatible `finish_reason`/`usage.completion_tokens`)
    can populate this same shape without pretending to have Ollama-
    specific concepts. `InferenceResult.completion` being `None` means
    the runtime reported nothing usable here - read `state`/`detail` for
    whether the call itself succeeded, never infer completion facts from
    output shape or absence of this field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Whether the runtime itself reported the generation as finished.
    #: Never inferred from output shape or length.
    completed: bool = True
    #: The runtime's own stated reason the generation ended (e.g. "stop",
    #: "length"), verbatim - never mapped to a taxonomy or acted on here.
    finish_reason: str = ""
    #: Tokens the runtime reports it generated for this call.
    output_token_count: int = 0
    #: Tokens the runtime reports it consumed from the prompt.
    prompt_token_count: int = 0


class InferenceResult(BaseModel):
    """The outcome of one bounded, real inference call. Never fabricated:
    `state` is `PASS` only when the runtime genuinely returned output within
    the caller's timeout."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime: str
    model_id: str
    state: HonestState
    detail: str
    elapsed_seconds: float = 0.0
    #: Truncated - evidence of genuine output, never the full generation, so a
    #: phase report never carries an unbounded or sensitive model output.
    output_excerpt: str = Field(default="", max_length=200)
    #: Full bounded response for the in-process consumer that requested the
    #: generation. Excluded from serialisation and repr so evidence/report code
    #: cannot accidentally persist unbounded model text; callers persist only
    #: validated, content-addressed artifacts.
    output: str = Field(default="", max_length=1_000_000, repr=False, exclude=True)
    #: F-0100. `None` when the runtime/adapter reports no completion facts
    #: (every call site that existed before this field, and any call that
    #: returned before a real response was ever received) - never guessed.
    completion: CompletionMetadata | None = None


@runtime_checkable
class LocalRuntimeAdapter(Protocol):
    """Structural contract every local runtime adapter satisfies.

    A `Protocol`, not an ABC a concrete adapter must inherit from - the same
    interface-inversion shape `control.capability.reference_resolution.
    ReferenceResolver` already uses for the identical reason: this context
    depends on a shape, and the composition root supplies whichever concrete
    adapters exist. At least two structurally distinct adapters implement this
    Protocol (`ollama_adapter.py`, `openai_compatible_adapter.py`), proving
    ARK-REQ-0016 by construction rather than by policy.
    """

    @property
    def runtime(self) -> str: ...

    def probe(self) -> RuntimeProbeResult: ...

    def list_models(self) -> tuple[LocalModelDescriptor, ...]: ...

    def infer(
        self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0
    ) -> InferenceResult: ...


__all__ = [
    "HonestState",
    "LocalModelDescriptor",
    "RuntimeProbeResult",
    "CompletionMetadata",
    "InferenceResult",
    "LocalRuntimeAdapter",
]
