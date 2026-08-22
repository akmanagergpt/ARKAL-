# Staged product generation — stage vocabulary

Owner: `engineering.factory`. Internal generation-pipeline sequencing only —
this is not a `CONTRACT_INVENTORY.md` entry and nothing outside
`engineering.factory` consumes it. It exists so the ordered stage list and
each stage's declared inputs live in exactly one place; `generation_stages.py`
parses this file at call time rather than repeating the list in Python
(the same reason `engineering.repair.failure_protocol` parses its stage
chain from a document instead of hard-coding it).

## Stages

### 1. backend_contract
Inputs: none
Rule: every route and data model implied by the blueprint's requirements is
declared as a machine-readable schema, not Python code — no route body,
no app instance, no decorator yet. Declare at least one JSON file under
backend/ whose content is a JSON array of route objects, each carrying
"path" and "method" ("GET"/"POST"/"PUT"/"DELETE"/"PATCH"); and at least
one JSON file under backend/ whose content is a JSON object describing a
data model, carrying a "fields" key. This is the real shape a real local
model produced unprompted for this exact rule (golden-work-045, frozen
evidence sha256:aabfc2e5f44758724d4941869eaccff28f3bfba18d76a5f39c044c32b7962eb5) —
codified here rather than fought, since a schema-first contract is not a
worse design than inline decorator stubs, only a different one this
pipeline had not yet declared explicitly.

### 2. backend_schema
Inputs: backend_contract
Rule: a real, executable SQLite schema or migration exists, generated from
backend_contract's data-model JSON, and is wired into the application's
real startup lifecycle, not a bare `CREATE TABLE` left outside any
lifecycle hook. This stage does not yet declare routes or an app
instance — that is backend_implementation's job, not this one's. Every
import in the file you write must resolve to a real Python module —
backend_contract's own JSON files (e.g. `backend/data_model.json`) are
schema *documents*, never Python modules, and must never be `import`ed;
read their real field names directly out of your own visible context and
write them as literal column/field names in real Python code
(golden-work-067, session evidence, frozen: a real qwen2.5-coder:14b
wrote `from backend.data_model import data_model` in `backend/db.py` —
never used anywhere in the file — and the real, first `pytest`
collection of this real candidate failed outright with
`ModuleNotFoundError: No module named 'backend.data_model'`).

### 3. backend_implementation
Inputs: backend_contract, backend_schema
Rule: a real application instance exists; every route declared in
backend_contract's route JSON has a real executable body that uses the
schema from backend_schema; every import resolves — backend_contract's
own JSON files are schema documents, never Python modules, and must
never be `import`ed (golden-work-067, session evidence, frozen: the
identical real defect as backend_schema's own rule cites, independently
repeated in `backend/app.py`) — the backend exposes an
executable server entrypoint. A route that inserts a new row and returns
JSON must include that row's own database-generated id (e.g.
cursor.lastrowid) in the response, not only the submitted request body
(golden-work-052/053, session evidence, frozen: a real model's own
generated test asserted the response includes an id its own create route
never returned). A route that fetches a single row with cursor.fetchone()
must convert it to a keyed object (e.g. conn.row_factory = sqlite3.Row
plus dict(row), or an explicit column-name mapping) before passing it to
jsonify — a bare tuple serializes as a JSON array, not an object with
named fields (golden-work-056, session evidence, frozen: a real model's
own generated test asserted a named field on exactly this shape and got
a real TypeError). dict(row) alone does not fix this: without
conn.row_factory = sqlite3.Row set on the connection first, dict() on a
plain tuple raises its own TypeError (golden-work-057, session evidence,
frozen: a real model wrapped every raw row in dict(row) but never set
row_factory, and every affected route returned HTTP 500). Cross-origin
access is not this stage's concern — that is backend_cors_boundary's
job, immediately after this one.

### 4. backend_cors_boundary
Inputs: backend_implementation
Rule: the sole job of this stage is real CORS middleware on the existing
application instance from backend_implementation — flask_cors's `CORS(app)`
for Flask, or Starlette/FastAPI's `CORSMiddleware`, permitting the
locally-served frontend this pipeline always produces. Return the complete,
updated application file with CORS added; change nothing else — routes,
schema and imports are already correct and are not this stage's concern.
Split out as its own stage (real evidence, golden-work-045, two consecutive
sessions): a real local model reliably produces routes+schema+entrypoint
together but did not reliably add CORS in the same bounded attempt even
when explicitly instructed to, twice; narrowing the stage to exactly one
concern is the fix, not raising the attempt budget or repeating the same
whole-stage prompt. No frontend stage may begin until this stage's own
narrow validation passes.

### 5. backend_tests
Inputs: backend_cors_boundary, backend_schema
Rule: at least one test file exists under the top-level tests/ path (not
backend/tests/ — the whole-product gate's required_roots checks the
top-level path segment, and golden-work-048 (session evidence, frozen)
reached that gate for the first time ever and failed it on exactly this:
a real qwen2.5-coder:14b placed its tests under backend/tests/test_app.py,
a reasonable Flask convention this rule never ruled out). Tests import
only symbols backend_cors_boundary's application actually exports,
declare every fixture they consume, enter the real application lifecycle
context required by startup hooks, and contain at least one real
assertion. A test that creates a row and later reads, updates or deletes
it by id must use the real id the create response actually returned
(e.g. `response.json['id']`), never a hardcoded literal such as `1` —
when a table's schema declares `AUTOINCREMENT` (backend_schema's own
common real choice), SQLite never reuses an id even after every row is
deleted between tests, so only the very first test that ever runs
against a fresh database genuinely gets id 1 (golden-work-070, session
evidence, frozen: three of eight real generated tests each independently
assumed their own freshly-created row was id 1; the alphabetically-first
of them passed, the other two failed a real 404 the exact same way).
Every name a test calls (e.g. `init_db()`) must be imported, defined or
assigned somewhere in that same test file — a real function existing
elsewhere in the codebase is not enough on its own (golden-work-071,
session evidence, frozen: `setUp()` called `init_db()`, a real function
genuinely defined in `backend/db.py`, but the file's own imports never
named it; real pytest collection failed all 8 tests outright with
`NameError: name 'init_db' is not defined`, the first thing every one of
them did).

### 6. product_ux_spec
Inputs: backend_contract
Rule: derive a machine-readable product UX specification at
`product/ux_spec.json` from backend_contract's own real declared routes
and data models — never a hard-coded product domain, never Dershane- or
Golden-Product-specific names. It is a planning artifact, not application
source: no JSX, no CSS, no component code. It must declare, as one JSON
object: `product_title`; `primary_roles` (at least one); `modules` (at
least one, one per backend_contract-declared data model — every declared
model must appear, and no module may name a model backend_contract never
declared), each with `name` (the model's own table name), `navigation_label`,
`presentation` (one of "table"/"card"/"list"), `actions` (the subset of
"create"/"edit"/"delete"/"view" the module's own backend resource really
supports — a module whose resource exposes POST must declare "create",
PUT/PATCH must declare "edit", DELETE must declare "delete"), `forms`
(required, each with `name` and `fields`, whenever `actions` includes
"create" or "edit"), `search_filter` (boolean), and `states` (`loading`,
`empty`, `error` booleans, plus `success` when the module has a mutating
action); `navigation_destinations` (every module's `navigation_label`, and
the dashboard's if one is declared); `dashboard` (optional — omit entirely
for a genuinely single-purpose product with nothing worth summarising;
when declared, carries `navigation_label`, `purpose` and `kpis`, each kpi
an object with `name` and `metric`, e.g.
`{"name": "Total Students", "metric": "count_students"}` — never a bare
string); and `design_system` (`typography_scale`, `spacing_scale`,
`component_conventions`, each a non-empty list of real conventions this
product's own frontend will use, plus `responsive` — true/false for
whether the layout must adapt to viewport width, or a named strategy
string such as "desktop-first" — and `accessible_focus_contrast`). Do not
force a dashboard or a multi-surface shell onto a real single-module
product — `dashboard` is optional and one module is a legal, complete
`modules` list. A backend-declared data model may be written either as
its own file (`{"table_name": "students", "fields": {...}}`) or nested
inside one file's `fields` object alongside others
(`{"fields": {"students": {...}, "courses": {...}}}`) — both are real,
already-observed backend_contract shapes (golden-work-064, session
evidence, frozen); a module must exist for every real model either shape
declares.

### 7. frontend_client
Inputs: backend_cors_boundary
Rule: a frontend API client exists with one real invokable function for
every route backend_cors_boundary's application actually exposes — each
function must itself send a real HTTP request (fetch or axios) using
that route's method, e.g. a function calling
`fetch(url, {method: 'POST', ...})` or `axios.post(url, ...)`. A route
descriptor or a route-to-string mapping object is not a call and does
not satisfy this rule (golden-work-054, session evidence, frozen: a real
qwen2.5-coder:14b wrote `{"createTask": "POST /tasks"}` — one JSON
property per route, never an actual invocation — identically on two
consecutive attempts).

### 8. frontend_ui
Inputs: frontend_client, backend_contract, product_ux_spec
Rule: the UI calls every function frontend_client exports and renders
loading, empty and error states. Render only field names backend_contract's
own data-model JSON actually declares (its "fields" object) — never invent
or guess one (golden-work-062, session evidence, frozen: a real model
rendered task.name in a JSX list item when the real declared model has no
"name" field, only "title" — every task rendered as a real, visibly empty
list item in a real browser, confirmed with a real running backend
returning real data). Also declare frontend/src/index.js that imports the
real component this stage just wrote and mounts it with
ReactDOM.render(<Component />, document.getElementById('root')) — no
other stage can write this correctly. golden-work-059 (session evidence,
frozen) found react-scripts build hard-codes src/index.js as its webpack
entry point and fails outright without it; golden-work-061 (session
evidence, frozen) then showed requiring it at manifests does not work —
manifests' own reduced context never sees this stage's real component
file name, only this stage does. Implement product_ux_spec's navigation
faithfully: every declared navigation destination (including the
dashboard's, if one is declared) must be reachable through a real
navigation element or a real interactive control. Never render only a
single bare list as the product's entire UI with the rest of
backend_contract's declared models unreachable (real evidence this
session, dershane-demo-003: backend_contract declared student, course
and payment models; the shipped frontend was one component rendering one
<ul> of student names, with no way to reach the other two anywhere in
the UI). Mutating forms, delete confirmation and post-mutation feedback
are not this stage's concern — that is frontend_forms's job, immediately
after this one.

### 9. frontend_forms
Inputs: frontend_client, frontend_ui, product_ux_spec
Rule: add real, labelled form UI, wired to frontend_client's real
create/update calls, for every module product_ux_spec declares a
"create" or "edit" action for, with a visible validation marker (never a
bare unlabelled input); for every module product_ux_spec declares a
"delete" action for, add a real delete control (e.g. a button) wired to
frontend_client's real delete call — this stage owns that control, not
just its confirmation step, since nothing upstream writes one — gated
behind a real confirmation step before it fires, when product_ux_spec
requires one (golden-work-069, session evidence, frozen: a real
qwen2.5-coder:14b's own real output for a module with a declared
"delete" action added no delete control of any kind, on two consecutive
real attempts — not a missing confirmation on an existing control, a
missing control); add a visible success/feedback marker after a
mutation completes. Return the
complete, updated frontend source — frontend_ui's own navigation,
dashboard and read-only rendering already work and are not this stage's
concern; add the missing mutation UI onto them, do not rewrite them. A
new route this stage adds under an existing broader route (e.g. adding
`/students/create` under frontend_ui's existing `/students`) must be
reachable, not silently shadowed: in a react-router v5 `<Switch>`, a
`<Route path='/students'>` with no `exact` matches `/students/create`
too and, being declared first, wins — the new route added under it never
renders. Either mark the broader existing route `exact` or place every
new, more specific route before it in the `<Switch>` (real evidence this
session, golden-work-068: `/students/create` and `/payments/create` were
both real, present routes rendering a real form component, and both were
completely unreachable in a real browser — `<Switch>` always rendered the
parent list route instead, on every navigation, silently). Split out as
its own stage (real evidence, golden-work-065): a real
qwen2.5-coder:14b reliably produced a genuine multi-module shell —
react-router navigation, a dashboard with real KPIs, loading/empty/error
states — but never once added product_ux_spec's declared create/edit/
delete forms in the same bounded attempt, across all 4 real attempts;
narrowing the stage to exactly the mutation-UI concern is the fix, the
same shape backend_cors_boundary's own split answered for backend
routes+schema-vs-CORS. A product whose product_ux_spec declares no
create/edit/delete action anywhere needs no change here — return
frontend_ui's own files unchanged rather than inventing one.

### 10. frontend_tests_config
Inputs: frontend_client, frontend_ui, frontend_forms
Rule: frontend tests, `package.json` and `config/README.md` are complete
and consistent with frontend_client, frontend_ui and frontend_forms.

### 11. manifests
Inputs: backend_contract, backend_schema, backend_implementation, backend_cors_boundary, backend_tests, product_ux_spec, frontend_client, frontend_ui, frontend_forms, frontend_tests_config
Rule: declared backend and frontend dependencies are compatible with each
other and with the target runtime, and the startup path is complete end to
end. This stage does not see the other stages' full source — sending all
eight stages' complete bytes here caused a real HTTP-level timeout, 4/4
attempts (golden-work-046). It receives instead: the real bytes of any
backend/requirements.txt, backend/pyproject.toml or frontend/package.json
already written, whether frontend/public/index.html already exists, and
two mechanically-extracted (not full-file) lists — every real third-party
package backend/*.py **and tests/*.py together** actually import, and
every real npm package frontend/src/* actually imports. Declare
backend/requirements.txt (or pyproject.toml) covering every extracted
import from that combined backend+tests list — a package a test file
alone imports (e.g. `pytest`) still needs declaring here; there is no
separate test-requirements file (golden-work-072, session evidence,
frozen: a real, genuinely idiomatic pytest test file wrote `import
pytest` and real `@pytest.fixture` usage; the real whole-product gate
refused the candidate outright with `tests/test_app.py imports
undeclared dependency 'pytest'`, since nothing had ever declared it) —
and reconcile frontend/package.json against the extracted frontend
imports; do not invent a dependency absent from either extracted list. Also declare
config/README.md with the exact real steps to install and start the
backend and frontend this pipeline actually produced — no other stage
owns this file, and golden-work-048 (session evidence, frozen) reached
the final whole-product gate for the first time ever and failed it on,
among other things, no config/README.md ever having been written. When
`_extracted/backend_entrypoint_module.txt` is present, config/README.md's
backend startup step must run it as a module from the project root using
that exact real name (e.g. `python -m backend.app`), never as a direct
script (`python backend/app.py`) — golden-work-067/068 (session evidence,
frozen): a real qwen2.5-coder:14b's own real backend used absolute
`backend.`-prefixed imports (`import backend.db`), legal, resolving
Python, that only resolve when the project root is on `sys.path`; direct
script invocation does not put it there and fails outright with
`ModuleNotFoundError`, module invocation does. When
frontend/package.json declares react-scripts, it must also declare a
scripts object with runnable "start" and "build" entries (e.g.
"react-scripts start" / "react-scripts build") — react-scripts alone as
a dependency is not runnable without them (golden-work-058, session
evidence, frozen: real "npm install" succeeded, then "npm run build"
failed outright with "Missing script: build", since package.json
declared no scripts object at all). The reverse must also hold: if
scripts calls "react-scripts start"/"react-scripts build",
"react-scripts" itself must be a real declared dependency or
devDependency, not merely referenced in the scripts commands
(golden-work-070, session evidence, frozen: scripts called
"react-scripts build" while "react-scripts" appeared in neither
dependencies nor devDependencies — real "npm install" silently installed
only the other three declared packages, and real "npm run build" failed
outright: "'react-scripts' is not recognized as an internal or external
command").
