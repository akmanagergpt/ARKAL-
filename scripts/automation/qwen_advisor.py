#!/usr/bin/env python3
"""Send stdin to the local Ollama advisory model without repository access."""

from __future__ import annotations

import json
import os
import sys
import urllib.request


def main() -> int:
    endpoint = os.environ.get(
        "ARKALI_OLLAMA_ENDPOINT", "http://127.0.0.1:11434/api/generate"
    )
    model = os.environ.get("ARKALI_LOCAL_MODEL", "qwen2.5-coder:14b")
    payload = json.dumps(
        {
            "model": model,
            "prompt": sys.stdin.read(),
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.1},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            result = json.load(response)
    except (OSError, ValueError) as exc:
        print(f"LOCAL_ADVISOR_UNAVAILABLE: {exc}", file=sys.stderr)
        return 1
    text = result.get("response")
    if not isinstance(text, str) or not text.strip():
        print("LOCAL_ADVISOR_INVALID_RESPONSE", file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
