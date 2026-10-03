"""Pure frontend source-shape helpers for UX preflight.

Owner: engineering.factory. Extracted from frontend_ux_preflight at a pure
source-analysis seam to restore the canonical module-size budget without
changing finding ownership or semantics.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.frontend_js_semantics import _commonjs_alias_export_names

_INLINE_EXPORT_PATTERN = re.compile(r"export\s+(?:const|(?:async\s+)?function)\s+(\w+)")
_GROUPED_EXPORT_BLOCK = re.compile(r"export\s*\{([^}]*)\}")
_COMMONJS_EXPORTS_BLOCK = re.compile(r"module\.exports\s*=\s*\{([^}]*)\}")
_UPDATE_OR_EDIT_NAME = re.compile(r"^(?:update|edit)", re.IGNORECASE)
_MUTATION_EXPORT_NAME = re.compile(r"^(?:create|update|edit|delete)", re.IGNORECASE)

def _exported_js_names(client_text: str) -> frozenset[str]:
    """Real names a JS/TS file exports, covering every real shape this
    pipeline's own generated `frontend_client` output has used: inline
    (`export function name(...)`/`export const name = ...`), grouped
    (`export { name, other as alias };` -- the local declared name, the
    one actually called or referenced elsewhere in the same file, not
    any renamed alias) and CommonJS (`module.exports = { name, ... };`
    -- golden-work-101, session evidence, frozen)."""
    names = set(_INLINE_EXPORT_PATTERN.findall(client_text))
    for block in _GROUPED_EXPORT_BLOCK.findall(client_text):
        for part in block.split(","):
            local_name = part.strip().split(" as ")[0].strip()
            if local_name:
                names.add(local_name)
    for block in _COMMONJS_EXPORTS_BLOCK.findall(client_text):
        for part in block.split(","):
            name = part.strip().split(":")[0].strip()
            if name:
                names.add(name)
    # F-0101 (real evidence: `factory-goal-mtz6bst2-myhr15`'s own
    # `apiClient.js`): `const api = {...}; module.exports = api;` -- see
    # `frontend_js_semantics._commonjs_alias_export_names`'s own docstring.
    return frozenset(names) | _commonjs_alias_export_names(client_text)

def _split_client_and_ui(files: Mapping[str, str]) -> tuple[str, str]:
    """A `*client*`-named file versus every other real `frontend/src/*`
    file -- moved here from `component_generation.py` (ADR-0008
    decomposition, not a GATE 8 exception: that module reached its
    400-logical-line ceiling, measured live by the real architecture
    gate, not assumed) to sit alongside every other real check that
    already needs this exact same split (`_frontend_ui_only_text`,
    `_update_like_client_exports`)."""
    client_paths = [
        path for path in files if path.startswith("frontend/src/") and "client" in path.lower()
    ]
    ui_paths = [
        path for path in files if path.startswith("frontend/src/") and "client" not in path.lower()
    ]
    client = "\n".join(files[path] for path in client_paths)
    ui = "\n".join(files[path] for path in ui_paths)
    return client, ui

def _frontend_ui_only_text(files: Mapping[str, str]) -> str:
    """Lowercased UI-only source (client files excluded) -- needed because
    a `*client*` file's own function DEFINITION (e.g. `async function
    updateStudent(...)`) would otherwise satisfy a regex looking for a
    real UI-side reference to it."""
    return _split_client_and_ui(files)[1].lower()

def _update_like_client_exports(files: Mapping[str, str]) -> frozenset[str]:
    """Real update/edit-named functions `frontend_client` actually exports
    -- golden-work-081 (session evidence, frozen): a real model reused one
    form component for both create and edit, passing the real exported
    `updateStudent` BY REFERENCE (`<StudentForm onSubmit={updateStudent}
    />`, invoked generically inside `StudentForm` as `onSubmit(...)`)
    rather than calling it directly by name (`updateStudent(...)`) -- a
    real, idiomatic React pattern this check's own first version (a regex
    requiring a literal `(` right after the name) rejected as a false
    positive on the very next real candidate. Matching the real declared
    name itself, the same mechanism `_unused_client_export_findings`
    already uses successfully, is robust to a call, a prop reference, or
    any other real way of using it."""
    client = "\n".join(
        source for path, source in files.items()
        if path.startswith("frontend/src/") and "client" in path.lower()
    )
    return frozenset(
        name for name in _exported_js_names(client)
        if _UPDATE_OR_EDIT_NAME.match(name)
    )

def _frontend_source_text(files: Mapping[str, str]) -> str:
    return "\n".join(
        source.lower() for path, source in files.items()
        if path.startswith("frontend/src/")
    )
