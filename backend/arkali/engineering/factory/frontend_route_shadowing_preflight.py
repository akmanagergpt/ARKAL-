"""Route-shadowing detection and repair for a generated react-router frontend.

Owner: `engineering.factory`. Moved out of `frontend_ux_preflight.py`
(ADR-0008 decomposition, not a GATE 8 exception): that module's own
403-logical-line ceiling, measured live by the real architecture-budget
gate, left no room for this session's new deterministic repair once a
real, reproduced full-attempt-budget exhaustion proved one was needed —
the same shape `frontend_client_call_preflight.py`/
`frontend_root_route_preflight.py` were already split out for earlier
this session.

golden-work-068 (real repository evidence, real qwen2.5-coder:14b,
frozen): frontend_ui wrote `<Route path='/students'>` with no `exact`;
frontend_forms then added `<Route path='/students/create'>` and
`<Route path='/students/edit/:id'>` after it in the same `<Switch>`. A
real browser navigated to `/students/create` and `/payments/create` and
rendered the parent list route both times — react-router's `<Switch>`
always matches the broader, un-exact route first, so the real, present
form component behind it never rendered at all, silently.

golden-work-096 (session evidence, frozen): a real qwen2.5-coder:14b
reproduced this exact, already-clearly-explained defect
(`<Route path='/tasks'>` with no `exact`, declared before
`<Route path='/tasks/create'>` in the same `<Switch>`) unchanged across
all 4 real `frontend_forms` attempts, exhausting the stage's full
attempt budget — proof the fix belonged to a deterministic repair, not
another blind retry, the same lesson golden-work-050/051 already
established for `Werkzeug<3`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.semantic_finding import SemanticFinding

#: react-router v5's <Switch> picks the FIRST matching Route in
#: declaration order; a Route with no `exact` matches any longer path
#: sharing its prefix. Text-level, not a real JSX parse -- deliberately
#: coarse, the same tolerance every other check in this bounded context
#: accepts.
_ROUTE_TAG = re.compile(r"<Route\s[^>]*?path=[\"']([^\"']+)[\"'][^>]*>")
_EXACT_ATTR = re.compile(r"(?<![\w-])exact(?![\w-])")


def _shadowed_route_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """A more specific route added under an existing broader one must
    actually be reachable. Runs unconditionally (no `product_ux_spec`
    dependency) — a general react-router correctness rule, not specific
    to the staged pipeline.
    """
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        routes = [
            (match.group(1), bool(_EXACT_ATTR.search(match.group(0))))
            for match in _ROUTE_TAG.finditer(source)
        ]
        for index, (route_path, exact) in enumerate(routes):
            if exact:
                continue
            prefix = route_path.rstrip("/") + "/"
            shadowed = next(
                (later for later, _ in routes[index + 1:] if later.startswith(prefix)), None,
            )
            if shadowed is not None:
                findings.append(SemanticFinding(
                    code="frontend_ui_route_shadowed", path=path,
                    detail=(
                        f"<Route path={route_path!r}> has no 'exact' and is declared "
                        f"before <Route path={shadowed!r}> in the same <Switch> — "
                        "react-router always matches the broader route first, so the "
                        "more specific route never renders"
                    ),
                ))
    return findings


def _repair_shadowed_route_in_source(source: str) -> str | None:
    """One file's own repair: adds `exact` to every broader, non-exact
    route this file's own shadowing shape proves shadows a later, more
    specific one -- rewritten back-to-front so earlier match spans stay
    valid after a later one grows in length. Returns `None` when nothing
    in this file needs it."""
    matches = list(_ROUTE_TAG.finditer(source))
    routes = [(m.group(1), bool(_EXACT_ATTR.search(m.group(0)))) for m in matches]
    to_fix: list[int] = []
    for index, (route_path, exact) in enumerate(routes):
        if exact:
            continue
        prefix = route_path.rstrip("/") + "/"
        if any(later.startswith(prefix) for later, _ in routes[index + 1:]):
            to_fix.append(index)
    if not to_fix:
        return None
    result = source
    for index in sorted(to_fix, reverse=True):
        match = matches[index]
        result = result[:match.start()] + match.group(0).replace(
            "<Route", "<Route exact", 1,
        ) + result[match.end():]
    return result


def _repair_shadowed_routes(stage_files: Mapping[str, str]) -> dict[str, str] | None:
    """Deterministic repair mirroring this pipeline's own Werkzeug<3-style
    repairs (golden-work-050/051's own lesson: once the exact, unambiguous
    fix for a real, verified defect is known, applying it and
    re-validating is more honest than another blind model retry). The
    fix is mechanically unambiguous once a real shadowing is proven by
    `_shadowed_route_findings` itself: inserting `exact` into the
    broader route's own tag makes it stop matching the more specific
    path it was swallowing, with no other real behavior change. Checked
    per file, the same shape shadowing itself is detected in — this
    pipeline has never produced a shadowing that spans two different
    files."""
    patched: dict[str, str] | None = None
    for path, source in stage_files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        repaired_source = _repair_shadowed_route_in_source(source)
        if repaired_source is None:
            continue
        if patched is None:
            patched = dict(stage_files)
        patched[path] = repaired_source
    return patched
