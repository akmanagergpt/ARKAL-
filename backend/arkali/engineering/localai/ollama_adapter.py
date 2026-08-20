"""Real Ollama adapter (ARK-REQ-0016, ARK-REQ-0129).

Owner: engineering.localai.

ONE OF AT LEAST TWO STRUCTURALLY DISTINCT ADAPTERS. This adapter speaks
Ollama's own native HTTP surface (`/api/tags`, `/api/version`, `/api/generate`)
- deliberately not the OpenAI-compatible shape `openai_compatible_adapter.py`
speaks against a different local runtime family, so the two adapters cannot be
collapsed into "one HTTP client with two base URLs" without losing the
protocol difference ARK-REQ-0016 requires be real.

LOOPBACK ONLY. The endpoint is validated at construction; a non-loopback host
is refused rather than accepted and caught later by policy
(`LocalRuntimeTargetNotLoopbackError`). This is a local-runtime adapter, not a
generic HTTP client.

READ-ONLY DISCOVERY, BOUNDED INFERENCE. `probe()` and `list_models()` issue
GET requests only and never change runtime state. `infer()` issues exactly one
POST with `stream: false` and the caller's timeout; a network failure, a
timeout or a non-200 response is an honest non-PASS outcome, never converted
to success.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from arkali.engineering.localai.adapter import (
    HonestState,
    InferenceResult,
    LocalModelDescriptor,
    RuntimeProbeResult,
)
from arkali.engineering.localai.errors import LocalRuntimeTargetNotLoopbackError

RUNTIME = "ollama"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_loopback(endpoint: str) -> bool:
    return urlparse(endpoint).hostname in _LOOPBACK_HOSTS


class OllamaAdapter:
    """`LocalRuntimeAdapter` over a real, locally-running Ollama server."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, *, json_mode: bool = False) -> None:
        if not _is_loopback(endpoint):
            raise LocalRuntimeTargetNotLoopbackError(
                f"ollama adapter endpoint {endpoint!r} is not loopback",
                source="MS §Local-Only mode",
            )
        self._endpoint = endpoint
        self._json_mode = json_mode

    @property
    def runtime(self) -> str:
        return RUNTIME

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def probe(self) -> RuntimeProbeResult:
        try:
            with urllib.request.urlopen(f"{self._endpoint}/api/version", timeout=3.0) as response:
                if response.status != 200:
                    return RuntimeProbeResult(
                        runtime=RUNTIME,
                        state=HonestState.EXTERNAL_UNAVAILABLE,
                        detail=f"unexpected status {response.status}",
                        endpoint=self._endpoint,
                    )
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return RuntimeProbeResult(
                runtime=RUNTIME,
                state=HonestState.NOT_CONFIGURED,
                detail=f"ollama not reachable at {self._endpoint}: {exc}",
                endpoint=self._endpoint,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return RuntimeProbeResult(
                runtime=RUNTIME,
                state=HonestState.EXTERNAL_UNAVAILABLE,
                detail=f"malformed response: {exc}",
                endpoint=self._endpoint,
            )
        return RuntimeProbeResult(
            runtime=RUNTIME,
            state=HonestState.PASS,
            detail=f"reachable, version {payload.get('version', 'unknown')}",
            endpoint=self._endpoint,
        )

    def list_models(self) -> tuple[LocalModelDescriptor, ...]:
        try:
            with urllib.request.urlopen(f"{self._endpoint}/api/tags", timeout=5.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            return ()
        found: list[LocalModelDescriptor] = []
        for entry in payload.get("models", []):
            details = entry.get("details", {})
            found.append(
                LocalModelDescriptor(
                    runtime=RUNTIME,
                    model_id=str(entry.get("name", entry.get("model", ""))),
                    parameter_size=str(details.get("parameter_size", "")),
                    quantization=str(details.get("quantization_level", "")),
                    context_length=int(details.get("context_length", 0) or 0),
                    endpoint=self._endpoint,
                )
            )
        return tuple(found)

    def infer(
        self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0
    ) -> InferenceResult:
        payload: dict[str, object] = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
        }
        if self._json_mode:
            payload["format"] = "json"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._endpoint}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                elapsed = time.monotonic() - started
                if response.status != 200:
                    return InferenceResult(
                        runtime=RUNTIME,
                        model_id=model_id,
                        state=HonestState.EXTERNAL_UNAVAILABLE,
                        detail=f"unexpected status {response.status}",
                        elapsed_seconds=elapsed,
                    )
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return InferenceResult(
                runtime=RUNTIME,
                model_id=model_id,
                state=HonestState.NOT_CONFIGURED,
                detail=f"inference call failed: {exc}",
                elapsed_seconds=time.monotonic() - started,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return InferenceResult(
                runtime=RUNTIME,
                model_id=model_id,
                state=HonestState.EXTERNAL_UNAVAILABLE,
                detail=f"malformed response: {exc}",
                elapsed_seconds=time.monotonic() - started,
            )
        text = str(payload.get("response", ""))
        return InferenceResult(
            runtime=RUNTIME,
            model_id=model_id,
            state=HonestState.PASS,
            detail="genuine local inference completed",
            elapsed_seconds=elapsed,
            output_excerpt=text[:200],
            output=text,
        )


__all__ = ["OllamaAdapter", "RUNTIME", "DEFAULT_ENDPOINT"]
