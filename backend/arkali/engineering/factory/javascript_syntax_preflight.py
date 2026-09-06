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

from arkali.engineering.factory.semantic_finding import SemanticFinding

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


#: F-0082 (`OBJECT_LITERAL_AT_STATEMENT_POSITION_GAP`). Real, live,
#: independently-reproduced evidence (`goal-mtoxjx1x-cwtlad` and
#: `goal-mtpjpadj-k9auqu`, `frontend_client`) that this exact class recurs
#: even with `STAGED_GENERATION_STAGES.md#7`'s own explicit prose warning
#: present on every attempt (the golden-work-054 citation already embedded
#: in that stage's own canonical rule text) and, since F-0077, the model's
#: own exact prior rejected bytes shown back to it too: a real
#: `qwen2.5-coder:14b` twice wrote a real object literal directly at the
#: top level of a `.js` file -- a route-to-string descriptor on one real
#: attempt, the same descriptor with a function-valued property on the
#: next real attempt -- real, `node`-verified `SyntaxError`s both times,
#: since a bare `{` at statement position parses as a BLOCK, never the
#: object literal it looks like (JavaScript's own grammar draws this
#: distinction only for `{`; a bare `[` is always a real, valid array-
#: literal expression statement either way, so it never needs or gets
#: this check). `_node_syntax_error` already, correctly, catches this as
#: invalid JS -- but its own detail text is a bare parser message
#: ("Unexpected token ':'"), giving the model a location and a mechanism,
#: never the SEMANTIC reason: prose describing a requirement, however
#: explicit, is not the same signal as a checker naming the actual
#: violated invariant (the identical lesson F-0069 already proved for
#: `frontend_forms`'s own structural findings).
#:
#: The extra check below is mechanically unambiguous, never a guess, and
#: strictly more general than a JSON-validity check (it also catches the
#: real function-valued variant above, which is not valid JSON at all):
#: it reuses `_node_syntax_error` itself, unchanged, against the SAME
#: source merely wrapped in parentheses. Wrapping in `(...)` is the exact,
#: real distinction JavaScript's own grammar already draws between "a `{`
#: opening a block/statement" (invalid here, since it is not a real
#: statement) and "a `{` opening a parenthesized EXPRESSION" (valid
#: whenever the content genuinely is a real object literal). If node
#: rejects the bare content but ACCEPTS the parenthesized form, the
#: content is, mechanically and unambiguously, a real object literal
#: sitting where a real statement (a function declaration, an assignment,
#: an export) was required -- never a guess about what the content "looks
#: like". Genuine, unrelated JS syntax mistakes (a missing semicolon, an
#: unclosed string, mismatched brackets) stay rejected in BOTH forms and
#: are never touched. Generic across every JS-producing stage that already
#: calls this shared checker (`frontend_client` today); no route, domain,
#: candidate or provider vocabulary appears anywhere.
def _is_object_literal_at_statement_position(source: str) -> bool:
    stripped = source.strip()
    if not stripped.startswith("{"):
        return False
    return _node_syntax_error(f"({source})") is None


def _javascript_syntax_findings(
    files: Mapping[str, str], *, path_prefix: str,
) -> list[SemanticFinding]:
    """Real `node --check` on every `.js`/`.jsx` file under `path_prefix`."""
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith(path_prefix) and path.endswith((".js", ".jsx"))):
            continue
        error = _node_syntax_error(source)
        if error is None:
            continue
        if _is_object_literal_at_statement_position(source):
            error += (
                " -- this file's own content is a real object literal written "
                "where a real statement was required (e.g. a function "
                "declaration, an assignment, or an export), never actually "
                "invoked or exported; write real JS/TS source that DOES "
                "something (a real function making a real HTTP call, "
                "assigned or exported), never a descriptor of what the code "
                "should do"
            )
        findings.append(SemanticFinding(code="javascript_syntax", path=path, detail=error))
    return findings
