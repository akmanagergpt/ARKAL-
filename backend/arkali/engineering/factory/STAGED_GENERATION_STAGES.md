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
instance — that is backend_implementation's job, not this one's.

### 3. backend_implementation
Inputs: backend_contract, backend_schema
Rule: a real application instance exists; every route declared in
backend_contract's route JSON has a real executable body that uses the
schema from backend_schema; every import resolves; the backend exposes an
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
assertion.

### 6. frontend_client
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

### 7. frontend_ui
Inputs: frontend_client
Rule: the UI calls every function frontend_client exports and renders
loading, empty and error states.

### 8. frontend_tests_config
Inputs: frontend_client, frontend_ui
Rule: frontend tests, `package.json` and `config/README.md` are complete
and consistent with frontend_client and frontend_ui.

### 9. manifests
Inputs: backend_contract, backend_schema, backend_implementation, backend_cors_boundary, backend_tests, frontend_client, frontend_ui, frontend_tests_config
Rule: declared backend and frontend dependencies are compatible with each
other and with the target runtime, and the startup path is complete end to
end. This stage does not see the other stages' full source — sending all
eight stages' complete bytes here caused a real HTTP-level timeout, 4/4
attempts (golden-work-046). It receives instead: the real bytes of any
backend/requirements.txt, backend/pyproject.toml or frontend/package.json
already written, whether frontend/public/index.html already exists, and
two mechanically-extracted (not full-file) lists — every real third-party
package backend/*.py actually imports, and every real npm package
frontend/src/* actually imports. Declare backend/requirements.txt (or
pyproject.toml) covering every extracted backend import, and reconcile
frontend/package.json against the extracted frontend imports; do not
invent a dependency absent from either extracted list. Also declare
config/README.md with the exact real steps to install and start the
backend and frontend this pipeline actually produced — no other stage
owns this file, and golden-work-048 (session evidence, frozen) reached
the final whole-product gate for the first time ever and failed it on,
among other things, no config/README.md ever having been written. When
frontend/package.json declares react-scripts, it must also declare a
scripts object with runnable "start" and "build" entries (e.g.
"react-scripts start" / "react-scripts build") — react-scripts alone as
a dependency is not runnable without them (golden-work-058, session
evidence, frozen: real "npm install" succeeded, then "npm run build"
failed outright with "Missing script: build", since package.json
declared no scripts object at all).
