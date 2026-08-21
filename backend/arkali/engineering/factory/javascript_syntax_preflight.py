"""Real `node --check` syntax validation for generated frontend JavaScript.

Owner: `engineering.factory`. golden-work-055 (session evidence, frozen):
a real qwen2.5-coder:14b wrote `frontend/src/apiClient.js` as a bare JSON
object literal — real, `node`-verified `SyntaxError: Unexpected token
':'` — and it passed the entire pipeline undetected: nothing here had
ever parsed frontend JS as JS, only matched substrings/regexes against
its text (`http_contract_preflight.frontend_contract_findings`'s own
`method: 'POST'` pattern happened to match a route descriptor embedded
inside a JSON string value, a real false negative). Mirrors
`component_generation._python_syntax_findings`'s own shape and the
identical class of gap that check closed for backend Python
(golden-work-045's real unterminated-string `SyntaxError`).

HONESTY. `node` is a real external binary, not always guaranteed present
(unlike Python's own `ast` module). When it cannot run, this returns no
findings for THIS check rather than fabricating a pass claim about JS
syntax — the same degrade-gracefully shape `dependency_resolution.py`
uses when `pip` itself is unavailable.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding

_NODE_TIMEOUT_SECONDS = 15.0
#: The real `node --check` output for a syntax error always names the exact
#: 1-indexed source line right after the file path, on its own line.
_LINE_NUMBER = re.compile(r":(\d+)$", re.M)
_SYNTAX_ERROR_LINE = re.compile(r"(?m)^SyntaxError:.*$")


def _node_syntax_error(source: str) -> str | None:
    fd, temp_path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(source)
        completed = subprocess.run(
            ["node", "--check", temp_path], capture_output=True, text=True,
            timeout=_NODE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        os.unlink(temp_path)
    if completed.returncode == 0:
        return None
    output = completed.stderr or completed.stdout
    # `node --check`'s own real output always leads with the temp file's
    # absolute path and the exact source line it failed on; only the
    # SyntaxError message itself is a useful, non-leaky finding detail.
    line = _LINE_NUMBER.search(output.split("\n", 1)[0])
    message = _SYNTAX_ERROR_LINE.search(output)
    if message is None:
        return output.strip()[:400]
    prefix = f"line {line.group(1)}: " if line else ""
    return prefix + message.group(0).strip()


def _javascript_syntax_findings(
    files: Mapping[str, str], *, path_prefix: str,
) -> list[SemanticFinding]:
    """Real `node --check` on every `.js`/`.jsx` file under `path_prefix`."""
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith(path_prefix) and path.endswith((".js", ".jsx"))):
            continue
        error = _node_syntax_error(source)
        if error is not None:
            findings.append(SemanticFinding(code="javascript_syntax", path=path, detail=error))
    return findings
