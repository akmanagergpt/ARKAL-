# Frontend source root

Phase 5 Package 4B delivers the **first** frontend increment: the Project
Registry page over the Command Center API (`ARK-REQ-0009`, `ARK-REQ-0178`, and
the frontend half of `ARK-REQ-0229`).

```
api/                 the one transport boundary
  contracts.ts       transport shapes; names match backend OpenAPI schemas
  client.ts          ArkaliApiClient; the only module that calls fetch
app/App.tsx          the shell
components/ui.tsx    the restrained presentation baseline
features/projects/   the Project Registry page, its state hook and its parts
```

**What lives here, and what does not.** This tree renders what the fabric
decided and asks the fabric to decide again. It holds no lifecycle transition
relation, no authorization rule and no data of its own. Those bans are enforced,
not merely stated — `backend/tests/structural/test_frontend_boundaries.py`,
`test_contract_drift.py` and `test_vertical_slice_linkage.py` read this source
against live backend authority and fail if any of it reappears.

Per `docs/canonical/ARCHITECTURE.md`, every capability phase from Phase 5 onward
delivers its own frontend increment; Phase 27 consolidates navigation and the
Beginner/Professional/Expert modes. This is one slice, not the Command Center.
