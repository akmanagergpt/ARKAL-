"""OpenAI-compatible local adapter (ARK-REQ-0016).

Owner: engineering.localai.

THE SECOND STRUCTURALLY DISTINCT ADAPTER. Where `ollama_adapter.py` speaks
Ollama's native surface, this adapter speaks the OpenAI-compatible REST shape
(`/v1/models`, `/v1/chat/completions`) that llama.cpp's `server`, LM Studio and
several other local runtimes expose. Different endpoint paths, different
request/response envelope, different default port - a real second transport,
not a renamed copy of the first. Together the two prove ARK-REQ-0016 ("no hard
dependency on one runtime") by construction: `engineering.localai`'s own
`LocalRuntimeAdapter` Protocol is satisfied by two runtimes that share no
transport code.

No runtime of this family is installed on the development host that produced
this phase; this adapter's `probe()` therefore honestly returns
`NOT_CONFIGURED` here, exactly as `control.isolation.backend_probe` returns
`NOT_CONFIGURED`/`UNSUPPORTED` for isolation backends this host cannot
provide. That is the correct answer, not a gap: the requirement is an
architectural property of the adapter layer, not a claim that every runtime is
present on every host.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from arkali.engineering.localai.adapter import (
    CompletionMetadata,
    HonestState,
    InferenceResult,
    LocalModelDescriptor,
    RuntimeProbeResult,
)
from arkali.engineering.localai.errors import LocalRuntimeTargetNotLoopbackError

RUNTIME = "openai_compatible"
DEFAULT_ENDPOINT = "http://127.0.0.1:8080"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
#: A conservative, generic parse of the trailing `<n>b` parameter-count
#: suffix many GGUF/Hugging-Face model ids declare in their own name (e.g.
#: `qwen/qwen3.5-9b` -> `9B`, `deepseek/deepseek-r1-0528-qwen3-8b` -> `8B`)
#: -- real data the provider itself put in the id, never guessed; honestly
#: empty for any id that does not carry this near-universal suffix (e.g.
#: `essentialai/rnj-1`).
_TRAILING_PARAMETER_COUNT = re.compile(r"(\d+(?:\.\d+)?)b(?:[-_]|$)", re.IGNORECASE)


def _is_loopback(endpoint: str) -> bool:
    return urlparse(endpoint).hostname in _LOOPBACK_HOSTS


def _parameter_size_from_id(model_id: str) -> str:
    match = _TRAILING_PARAMETER_COUNT.search(model_id)
    return f"{match.group(1)}B" if match else ""


class OpenAICompatibleAdapter:
    """`LocalRuntimeAdapter` over a real, locally-running OpenAI-compatible
    server (e.g. llama.cpp's `server`, LM Studio)."""

    def __init__(
        self, endpoint: str = DEFAULT_ENDPOINT, *,
        max_output_tokens: int | None = None, json_mode: bool = False,
        reasoning_effort: str | None = None,
    ) -> None:
        if not _is_loopback(endpoint):
            raise LocalRuntimeTargetNotLoopbackError(
                f"openai-compatible adapter endpoint {endpoint!r} is not loopback",
                source="MS §Local-Only mode",
            )
        self._endpoint = endpoint
        self._max_output_tokens = max_output_tokens
        self._json_mode = json_mode
        #: The standard OpenAI `reasoning_effort` field (real, documented,
        #: provider-agnostic -- never a Qwen-specific name), forwarded
        #: unchanged when set. Real evidence, this session: a reasoning
        #: model's own hidden `reasoning_content` can consume an entire
        #: small output-token budget before any visible content is ever
        #: produced; `reasoning_effort="none"`, verified live against
        #: Bionic, empties `reasoning_content` and returns the real
        #: visible answer immediately. `None` (default) sends no such
        #: field at all -- byte-identical prior request shape for every
        #: existing caller.
        self._reasoning_effort = reasoning_effort

    @property
    def runtime(self) -> str:
        return RUNTIME

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def probe(self) -> RuntimeProbeResult:
        try:
            with urllib.request.urlopen(
                f"{self._endpoint}/v1/models", timeout=3.0
            ) as response:
                if response.status != 200:
                    return RuntimeProbeResult(
                        runtime=RUNTIME, state=HonestState.EXTERNAL_UNAVAILABLE,
                        detail=f"unexpected status {response.status}",
                        endpoint=self._endpoint,
                    )
                json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return RuntimeProbeResult(
                runtime=RUNTIME, state=HonestState.NOT_CONFIGURED,
                detail=f"no OpenAI-compatible server reachable at "
                       f"{self._endpoint}: {exc}",
                endpoint=self._endpoint,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return RuntimeProbeResult(
                runtime=RUNTIME, state=HonestState.EXTERNAL_UNAVAILABLE,
                detail=f"malformed response: {exc}", endpoint=self._endpoint,
            )
        return RuntimeProbeResult(
            runtime=RUNTIME, state=HonestState.PASS,
            detail="reachable", endpoint=self._endpoint,
        )

    def _native_model_metadata(self) -> dict[str, dict[str, object]]:
        """LM Studio's own richer `/api/v0/models` surface, when the local
        server exposes it -- real `quantization`/`max_context_length` facts
        the plain OpenAI-compatible `/v1/models` shape cannot carry. Not
        every OpenAI-compatible server is LM Studio; honestly empty (never
        raising) when this native endpoint does not exist here, so
        `list_models` falls back to its own prior, unchanged shape."""
        try:
            with urllib.request.urlopen(
                f"{self._endpoint}/api/v0/models", timeout=5.0
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                json.JSONDecodeError):
            return {}
        return {str(entry.get("id", "")): entry for entry in payload.get("data", [])}

    def list_models(self) -> tuple[LocalModelDescriptor, ...]:
        try:
            with urllib.request.urlopen(
                f"{self._endpoint}/v1/models", timeout=5.0
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                json.JSONDecodeError):
            return ()
        native = self._native_model_metadata()
        found: list[LocalModelDescriptor] = []
        for entry in payload.get("data", []):
            model_id = str(entry.get("id", ""))
            native_entry = native.get(model_id, {})
            found.append(LocalModelDescriptor(
                runtime=RUNTIME, model_id=model_id,
                parameter_size=_parameter_size_from_id(model_id),
                quantization=str(native_entry.get("quantization", "")),
                context_length=int(native_entry.get("max_context_length", 0) or 0),
                endpoint=self._endpoint,
            ))
        return tuple(found)

    def infer(
        self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0
    ) -> InferenceResult:
        payload: dict[str, object] = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self._max_output_tokens is not None:
            payload["max_tokens"] = self._max_output_tokens
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self._reasoning_effort is not None:
            payload["reasoning_effort"] = self._reasoning_effort
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._endpoint}/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(
                request, timeout=timeout_seconds
            ) as response:
                elapsed = time.monotonic() - started
                if response.status != 200:
                    return InferenceResult(
                        runtime=RUNTIME, model_id=model_id,
                        state=HonestState.EXTERNAL_UNAVAILABLE,
                        detail=f"unexpected status {response.status}",
                        elapsed_seconds=elapsed,
                    )
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return InferenceResult(
                runtime=RUNTIME, model_id=model_id, state=HonestState.NOT_CONFIGURED,
                detail=f"inference call failed: {exc}",
                elapsed_seconds=time.monotonic() - started,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return InferenceResult(
                runtime=RUNTIME, model_id=model_id,
                state=HonestState.EXTERNAL_UNAVAILABLE,
                detail=f"malformed response: {exc}",
                elapsed_seconds=time.monotonic() - started,
            )
        choices = payload.get("choices", [])
        text = ""
        finish_reason = ""
        if choices:
            text = str(choices[0].get("message", {}).get("content", ""))
            finish_reason = str(choices[0].get("finish_reason", ""))
        usage = payload.get("usage", {})
        completion = CompletionMetadata(
            completed=finish_reason != "",
            finish_reason=finish_reason,
            output_token_count=int(usage.get("completion_tokens", 0) or 0),
            prompt_token_count=int(usage.get("prompt_tokens", 0) or 0),
        )
        return InferenceResult(
            runtime=RUNTIME, model_id=model_id, state=HonestState.PASS,
            detail="genuine local inference completed", elapsed_seconds=elapsed,
            output_excerpt=text[:200], output=text, completion=completion,
        )


__all__ = ["OpenAICompatibleAdapter", "RUNTIME", "DEFAULT_ENDPOINT"]
