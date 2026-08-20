# C-35 — Command Center HTTP API consolidation

**Owner:** `surfaces.command`  
**Phase:** 27  
**Compatibility:** ADDITIVE

## Scope

C-35 consolidates the already-shipping Command Center browser slices. It does
not introduce another registry, workflow authority, state machine, PDP/PEP, or
backend orchestration layer.

The browser continues to consume the existing real routes:

- Project Registry: `/api/projects`, `/api/lifecycle/project`
- Workflow Studio: `/api/workflows/{workflow_id}` and its revision/execution
  routes

The canonical fourteen areas are visible in one navigation system. An area is
actionable only when this frontend has a real connected surface for it;
otherwise it is disabled and labelled `Yakında`. No disabled area renders a
success, metric, state, or action.

## Skill modes

The canonical source names Beginner, Professional, and Expert but specifies no
finer behaviour. The implementation therefore records the following as a
product/engineering decision, not a new canonical requirement:

- **Başlangıç (Beginner)** is the default, asks what the user wants to do, and
  hides internal identifiers and Workflow Studio.
- **Profesyonel (Professional)** keeps project-management surfaces available
  while withholding low-level workflow controls.
- **Uzman (Expert)** exposes Workflow Studio and internal project/revision
  identities.

Changing mode changes presentation and navigation only. It never creates or
changes backend capability. Leaving Expert while Workflow Studio is open
returns safely to the Command Center.

## Real-state rule

All project lifecycle, revision, workflow graph, execution, and refusal state
is returned by the existing backend. The frontend neither reconstructs state
machine transitions nor fabricates unavailable capability. Production browser
evidence exercises a Vite production build, live FastAPI process, real
Alembic-migrated SQLite database, and Chromium without request interception.

## Explicitly not built

No live goal-to-product orchestrator, worker loop, local-model execution,
generated-product live preview, provider registry, agent runtime, or deployment
surface is added. `DEF-009` remains open and unaffected.

