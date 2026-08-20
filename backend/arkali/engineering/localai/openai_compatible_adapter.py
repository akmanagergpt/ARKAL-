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

RUNTIME = "openai_compatible"
DEFAULT_ENDPOINT = "http://127.0.0.1:8080"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_loopback(endpoint: str) -> bool:
    return urlparse(endpoint).hostname in _LOOPBACK_HOSTS


class OpenAICompatibleAdapter:
    """`LocalRuntimeAdapter` over a real, locally-running OpenAI-compatible
    server (e.g. llama.cpp's `server`, LM Studio)."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT) -> None:
        if not _is_loopback(endpoint):
            raise LocalRuntimeTargetNotLoopbackError(
                f"openai-compatible adapter endpoint {endpoint!r} is not loopback",
                source="MS §Local-Only mode",
            )
        self._endpoint = endpoint

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

    def list_models(self) -> tuple[LocalModelDescriptor, ...]:
        try:
            with urllib.request.urlopen(
                f"{self._endpoint}/v1/models", timeout=5.0
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                json.JSONDecodeError):
            return ()
        found: list[LocalModelDescriptor] = []
        for entry in payload.get("data", []):
            found.append(LocalModelDescriptor(
                runtime=RUNTIME, model_id=str(entry.get("id", "")),
                endpoint=self._endpoint,
            ))
        return tuple(found)

    def infer(
        self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0
    ) -> InferenceResult:
        body = json.dumps({
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
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
        if choices:
            text = str(choices[0].get("message", {}).get("content", ""))
        return InferenceResult(
            runtime=RUNTIME, model_id=model_id, state=HonestState.PASS,
            detail="genuine local inference completed", elapsed_seconds=elapsed,
            output_excerpt=text[:200], output=text,
        )


__all__ = ["OpenAICompatibleAdapter", "RUNTIME", "DEFAULT_ENDPOINT"]
