"""Real, behavioral proof for F-0064-preflight's "declared-capability
coverage" fix to `run_golden_browser_journey.mjs` (gap 7, module docstring)
-- never a static substring check alone.

WHY THIS EXISTS. A real ARKALI LIVE PRODUCT CHECKPOINT found the acceptance
journey's own related-resource-create step silently skipped when the
control was missing (`if (await relatedCreate.count())`), and its edit step
never verified the form showed the record's own real data before typing
over it. Both are now fixed generically, keyed on `_AcceptanceScenario`'s
real `actions` field (`acceptance_plan_compiler.py`'s own already-computed,
spec+backend-reconciled result) -- never a per-product special case. This
module proves the FIX, not the historical bug, against two synthetic,
completely unrelated domains, running the real, unmodified
`run_golden_browser_journey.mjs` as a real subprocess against a real
(stdlib-only, no framework) backend and a real static frontend server, a
real Chromium instance underneath (the same `@playwright/test` install the
journey itself already requires from `frontend/node_modules`) -- never a
mock of the journey's own logic.

Domain-neutral by construction: two structurally different resource/field
shapes (`widgets`/`gadgets` and `notes`/`tags`) prove nothing here is
keyed on the historical `students`/`payments` names.
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
JOURNEY = REPO / "scripts" / "run_golden_browser_journey.mjs"
BACKEND_PORT = 5000
FRONTEND_PORT = 3000


def _free(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _wait_http(url: str, timeout: float = 10.0) -> None:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    raise RuntimeError(f"fixture server never answered {url}")


class _Store:
    """A trivial, real, in-memory REST resource -- no framework, no mock:
    genuine HTTP semantics (real status codes, real JSON bodies, real
    incrementing ids), just no persistence beyond the process lifetime."""

    def __init__(self) -> None:
        self.rows: dict[str, list[dict]] = {}
        self.next_id: dict[str, int] = {}

    def create(self, resource: str, payload: dict) -> dict:
        self.next_id[resource] = self.next_id.get(resource, 0) + 1
        row = {"id": self.next_id[resource], **payload}
        self.rows.setdefault(resource, []).append(row)
        return row

    def list(self, resource: str) -> list[dict]:
        return self.rows.get(resource, [])

    def get(self, resource: str, item_id: int) -> dict | None:
        return next((r for r in self.rows.get(resource, []) if r["id"] == item_id), None)

    def update(self, resource: str, item_id: int, payload: dict) -> dict | None:
        row = self.get(resource, item_id)
        if row is None:
            return None
        row.update(payload)
        return row

    def delete(self, resource: str, item_id: int) -> bool:
        rows = self.rows.get(resource, [])
        before = len(rows)
        self.rows[resource] = [r for r in rows if r["id"] != item_id]
        return len(self.rows[resource]) != before


def _make_backend_handler(store: _Store) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # noqa: ANN401
            pass

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _json(self, status: int, body: object) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(200)
            self._cors()
            self.end_headers()

        def _parts(self) -> list[str]:
            return [p for p in self.path.split("?")[0].split("/") if p]

        def do_GET(self) -> None:  # noqa: N802
            parts = self._parts()
            if len(parts) == 1:
                self._json(200, store.list(parts[0]))
            elif len(parts) == 2:
                row = store.get(parts[0], int(parts[1]))
                self._json(200 if row else 404, row or {"error": "not found"})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            parts = self._parts()
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            row = store.create(parts[0], payload)
            self._json(201, row)

        def do_PUT(self) -> None:  # noqa: N802
            parts = self._parts()
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            row = store.update(parts[0], int(parts[1]), payload)
            self._json(200 if row else 404, row or {"error": "not found"})

        def do_DELETE(self) -> None:  # noqa: N802
            parts = self._parts()
            ok = store.delete(parts[0], int(parts[1]))
            self._json(200 if ok else 404, {"deleted": ok})

    return Handler


def _label_input(field: str) -> str:
    return f'<label for="{field}">{field}</label><input id="{field}" name="{field}" />'


def _list_page(
    resource: str, singular: str, rows: list[dict], display_field: str,
    *, create_control: bool, delete_control: bool, primary: str, related: str | None,
) -> str:
    items = "".join(
        f'<li>{row.get(display_field, "")} '
        f'<a href="/{resource}/edit/{row["id"]}">Edit</a>'
        + (f' <button data-id="{row["id"]}" class="delete-btn">Delete</button>' if delete_control else "")
        + "</li>"
        for row in rows
    )
    create_link = f'<a href="/{resource}/create">Create {singular}</a>' if create_control else ""
    delete_script = (
        """
        <script>
        document.querySelectorAll('.delete-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                if (window.confirm('Are you sure?')) {
                    fetch('http://localhost:5000/%s/' + btn.dataset.id, {method: 'DELETE'})
                        .then(function() { window.location.href = '/%s'; });
                }
            });
        });
        </script>
        """ % (resource, resource)
        if delete_control else ""
    )
    return (
        f"<html><body>{_nav(primary, related)}<h1>{resource}</h1>{create_link}<ul>{items}</ul>"
        f"{delete_script}</body></html>"
    )


def _nav(primary: str, related: str | None) -> str:
    related_item = f'<li><a href="/{related}">Related</a></li>' if related else ""
    return f"""
<nav>
  <ul>
    <li><a href="/">Dashboard</a></li>
    <li><a href="/{primary}">Primary</a></li>
    {related_item}
  </ul>
</nav>
"""


def _validation_guard(fields: tuple[str, ...]) -> str:
    checks = " || ".join(f"!document.getElementById('{f}').value" for f in fields)
    return f"if ({checks}) {{ return; }}" if fields else ""


def _form_page(
    resource: str, fields: tuple[str, ...], submit_label: str, action_js: str,
    *, primary: str, related: str | None,
) -> str:
    inputs = "".join(_label_input(f) for f in fields)
    return f"""<html><body>{_nav(primary, related)}<form id="f">{inputs}
    <button type="submit">{submit_label}</button></form>
    <script>
    document.getElementById('f').addEventListener('submit', function(e) {{
        e.preventDefault();
        {_validation_guard(fields)}
        var payload = {{}};
        {"".join(f"payload['{f}'] = document.getElementById('{f}').value;" for f in fields)}
        {action_js}
    }});
    </script>
    </body></html>"""


def _make_frontend_handler(
    *,
    primary: str, primary_singular: str, primary_fields: tuple[str, ...], primary_display: str,
    related: str | None, related_singular: str, related_fields: tuple[str, ...],
    related_relationship_field: str = "",
    related_create_control: bool,
    edit_prefill_correct: bool,
    store: _Store,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # noqa: ANN401
            pass

        def _html(self, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            parts = [p for p in path.split("/") if p]

            if path == "/":
                self._html(f"<html><body>{_nav(primary, related)}<h2>Dashboard</h2></body></html>")
                return

            if parts and parts[0] == primary:
                self._route_resource(
                    parts, primary, primary_singular, primary_fields, primary_display,
                    create_control=True, prefill_correct=edit_prefill_correct,
                )
                return

            if related and parts and parts[0] == related:
                self._route_resource(
                    parts, related, related_singular, related_fields, related_fields[0],
                    create_control=related_create_control, prefill_correct=True,
                    create_extra_fields=(related_relationship_field,) if related_relationship_field else (),
                )
                return

            self._html("<html><body>not found</body></html>")

        def _route_resource(
            self, parts: list[str], resource: str, singular: str, fields: tuple[str, ...],
            display_field: str, *, create_control: bool, prefill_correct: bool,
            create_extra_fields: tuple[str, ...] = (),
        ) -> None:
            if len(parts) == 1:
                self._html(_list_page(
                    resource, singular, store.list(resource), display_field,
                    create_control=create_control, delete_control=(resource == primary),
                    primary=primary, related=related,
                ))
                return
            if len(parts) == 2 and parts[1] == "create":
                action = (
                    "fetch('http://localhost:5000/%s', {method:'POST', "
                    "headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})"
                    ".then(function(){ window.location.href = '/%s'; });" % (resource, resource)
                )
                self._html(_form_page(
                    resource, fields + create_extra_fields, f"Create {singular}", action,
                    primary=primary, related=related,
                ))
                return
            if len(parts) == 3 and parts[1] == "edit":
                item_id = parts[2]
                row = store.get(resource, int(item_id)) or {}
                inputs = "".join(_label_input(f) for f in fields)
                prefill_js = "".join(
                    f"document.getElementById('{f}').value = {json.dumps(str(row.get(f, '')) if prefill_correct else '')};"
                    for f in fields
                )
                action = (
                    "fetch('http://localhost:5000/%s/%s', {method:'PUT', "
                    "headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})"
                    ".then(function(){ window.location.href = '/%s'; });" % (resource, item_id, resource)
                )
                self._html(f"""<html><body>{_nav(primary, related)}<form id="f">{inputs}
                <button type="submit">Submit</button></form>
                <script>
                {prefill_js}
                document.getElementById('f').addEventListener('submit', function(e) {{
                    e.preventDefault();
                    var payload = {{}};
                    {"".join(f"payload['{f}'] = document.getElementById('{f}').value;" for f in fields)}
                    {action}
                }});
                </script>
                </body></html>""")
                return
            self._html("<html><body>not found</body></html>")

    return Handler


def _scenario_json(
    tmp_path: pathlib.Path, *, primary: str, primary_singular: str, primary_fields: tuple[str, ...],
    related: str | None, related_singular: str, related_fields: tuple[str, ...],
    related_relationship_field: str, related_actions: tuple[str, ...],
) -> pathlib.Path:
    scenario = {
        "scenario_id": "capability-coverage-fixture",
        "resources": [
            {
                "name": primary, "collection_route": f"/{primary}", "navigation_label": "Primary",
                "singular_label": primary_singular, "editable_form_fields": list(primary_fields),
                "destructive_confirmation_required": True, "actions": ["create", "edit", "delete", "view"],
            },
        ] + (
            [{
                "name": related, "collection_route": f"/{related}", "navigation_label": "Related",
                "singular_label": related_singular, "editable_form_fields": list(related_fields),
                "destructive_confirmation_required": False,
                "relationship_fields": {related_relationship_field: primary},
                "actions": list(related_actions),
            }] if related else []
        ),
        "primary_resource": primary,
        "create_payload": {f: "x" for f in primary_fields},
        "update_payload": {f: "y" for f in primary_fields},
        "related_resource": related,
        "related_create_payload": {f: "x" for f in related_fields} if related else None,
        "navigation_destinations": ["Primary", "Related", "Dashboard"] if related else ["Primary", "Dashboard"],
        "browser_create_values": {f: f"browser-create-{f}" for f in primary_fields},
        "browser_update_values": {primary_fields[0]: f"browser-update-{primary_fields[0]}"},
        "browser_related_values": {f: f"browser-related-{f}" for f in related_fields} if related else None,
    }
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    return path


def _run_journey(
    tmp_path: pathlib.Path, *, primary: str, primary_singular: str, primary_fields: tuple[str, ...],
    related: str | None = None, related_singular: str = "", related_fields: tuple[str, ...] = (),
    related_relationship_field: str = "", related_actions: tuple[str, ...] = (),
    related_create_control: bool = True, edit_prefill_correct: bool = True,
) -> subprocess.CompletedProcess:
    if not _free(BACKEND_PORT) or not _free(FRONTEND_PORT):
        pytest.skip(f"ports {BACKEND_PORT}/{FRONTEND_PORT} are not free on this host")

    store = _Store()
    primary_seed = store.create(primary, {f: f"seed-{f}" for f in primary_fields})
    if related:
        store.create(related, {related_relationship_field: primary_seed["id"], **{f: f"seed-{f}" for f in related_fields}})

    backend = ThreadingHTTPServer(("127.0.0.1", BACKEND_PORT), _make_backend_handler(store))
    frontend = ThreadingHTTPServer(("127.0.0.1", FRONTEND_PORT), _make_frontend_handler(
        primary=primary, primary_singular=primary_singular, primary_fields=primary_fields,
        primary_display=primary_fields[0],
        related=related, related_singular=related_singular, related_fields=related_fields,
        related_relationship_field=related_relationship_field,
        related_create_control=related_create_control, edit_prefill_correct=edit_prefill_correct,
        store=store,
    ))
    backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
    frontend_thread = threading.Thread(target=frontend.serve_forever, daemon=True)
    backend_thread.start()
    frontend_thread.start()
    try:
        _wait_http(f"http://127.0.0.1:{BACKEND_PORT}/{primary}")
        _wait_http(f"http://127.0.0.1:{FRONTEND_PORT}/")

        scenario_path = _scenario_json(
            tmp_path, primary=primary, primary_singular=primary_singular, primary_fields=primary_fields,
            related=related, related_singular=related_singular, related_fields=related_fields,
            related_relationship_field=related_relationship_field, related_actions=related_actions,
        )
        return subprocess.run(
            [
                "node", str(JOURNEY), "--candidate", "capability-coverage-fixture",
                "--scenario", str(scenario_path), "--primary-id", str(primary_seed["id"]),
            ],
            cwd=REPO, capture_output=True, text=True, timeout=60,
        )
    finally:
        backend.shutdown()
        frontend.shutdown()
        backend_thread.join(timeout=5)
        frontend_thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Domain A: widgets / gadgets -- structurally unlike Student/Payment on
# purpose (different field names, different relationship field name).
# ---------------------------------------------------------------------------

def _domain_a(tmp_path: pathlib.Path, **overrides: object) -> subprocess.CompletedProcess:
    kwargs = dict(
        primary="widgets", primary_singular="Widget", primary_fields=("label",),
        related="gadgets", related_singular="Gadget", related_fields=("note",),
        related_relationship_field="widget_id", related_actions=("create", "view"),
    )
    kwargs.update(overrides)
    return _run_journey(tmp_path, **kwargs)


class TestMandatoryRelatedCreateCoverage:
    def test_a_mandatory_create_declared_control_missing_fails(self, tmp_path: pathlib.Path) -> None:
        """item A."""
        result = _domain_a(tmp_path, related_create_control=False)
        assert result.returncode != 0, result.stdout + result.stderr
        assert "mandatory" in (result.stdout + result.stderr).lower()
        assert "gadgets" in (result.stdout + result.stderr)

    def test_b_mandatory_create_declared_control_exists_passes(self, tmp_path: pathlib.Path) -> None:
        """item B."""
        result = _domain_a(tmp_path, related_create_control=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "BROWSER_JOURNEY_PASS" in result.stdout

    def test_e_genuinely_optional_related_create_is_a_legitimate_skip(self, tmp_path: pathlib.Path) -> None:
        """item E: related resource never declares "create" at all -- no
        control is rendered, and the journey must complete anyway."""
        result = _domain_a(tmp_path, related_actions=("view",), related_create_control=False)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "BROWSER_JOURNEY_PASS" in result.stdout


class TestEditPrefillCoverage:
    def test_c_wrong_or_empty_prefill_fails(self, tmp_path: pathlib.Path) -> None:
        """item C."""
        result = _domain_a(tmp_path, edit_prefill_correct=False)
        assert result.returncode != 0, result.stdout + result.stderr
        combined = (result.stdout + result.stderr).lower()
        assert "pre-populated" in combined or "does not show" in combined

    def test_d_correct_prefill_lets_the_journey_continue_and_pass(self, tmp_path: pathlib.Path) -> None:
        """item D."""
        result = _domain_a(tmp_path, edit_prefill_correct=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "BROWSER_JOURNEY_PASS" in result.stdout


class TestSecondDomainProvesNoHardcoding:
    def test_f_a_structurally_different_domain_behaves_identically(self, tmp_path: pathlib.Path) -> None:
        """item F: completely different resource/field/relationship names
        (`notes`/`tags`, `tag_id`) exercise the identical unmodified journey
        code and reach the identical PASS/FAIL outcomes."""
        def domain_b(**overrides: object) -> subprocess.CompletedProcess:
            kwargs = dict(
                primary="notes", primary_singular="Note", primary_fields=("body",),
                related="tags", related_singular="Tag", related_fields=("name",),
                related_relationship_field="note_id", related_actions=("create", "view"),
            )
            kwargs.update(overrides)
            return _run_journey(tmp_path, **kwargs)

        missing = domain_b(related_create_control=False)
        assert missing.returncode != 0, missing.stdout + missing.stderr
        assert "mandatory" in (missing.stdout + missing.stderr).lower()

        working = domain_b(related_create_control=True)
        assert working.returncode == 0, working.stdout + working.stderr
        assert "BROWSER_JOURNEY_PASS" in working.stdout

        bad_prefill = domain_b(edit_prefill_correct=False)
        assert bad_prefill.returncode != 0, bad_prefill.stdout + bad_prefill.stderr


class TestExistingValidJourneyStillPasses:
    def test_g_a_fully_correct_journey_with_no_related_resource_still_passes(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """item G: regression -- a legitimate single-resource product (no
        related resource at all) is unaffected by either fix."""
        result = _run_journey(
            tmp_path, primary="records", primary_singular="Record", primary_fields=("title",),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "BROWSER_JOURNEY_PASS" in result.stdout
