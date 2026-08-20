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
declared as a signature only — path, method, model fields — with no route
body implemented yet.

### 2. backend_schema
Inputs: backend_contract
Rule: a real, executable SQLite schema or migration exists and is wired
into the application's real startup lifecycle, not a bare `CREATE TABLE`
left outside any lifecycle hook.

### 3. backend_implementation
Inputs: backend_contract, backend_schema
Rule: every route declared in backend_contract has a real executable body
that uses the schema from backend_schema; every import resolves; the
backend exposes an executable server entrypoint.

### 4. backend_tests
Inputs: backend_implementation, backend_schema
Rule: tests import only symbols backend_implementation actually exports,
declare every fixture they consume, enter the real application lifecycle
context required by startup hooks, and contain at least one real assertion.

### 5. frontend_client
Inputs: backend_implementation
Rule: a frontend API client exists with one call for every route
backend_implementation actually exposes, and a CORS/origin policy
consistent with the frontend running on a separate origin.

### 6. frontend_ui
Inputs: frontend_client
Rule: the UI calls every function frontend_client exports and renders
loading, empty and error states.

### 7. frontend_tests_config
Inputs: frontend_client, frontend_ui
Rule: frontend tests, `package.json` and `config/README.md` are complete
and consistent with frontend_client and frontend_ui.

### 8. manifests
Inputs: backend_contract, backend_schema, backend_implementation, backend_tests, frontend_client, frontend_ui, frontend_tests_config
Rule: declared backend and frontend dependencies are compatible with each
other and with the target runtime, and the startup path is complete end to
end.
