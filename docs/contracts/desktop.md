# Phase 28 — Tauri Desktop architecture

**Owner:** `surfaces.command`  
**Phase:** 28  
**Compatibility:** ADDITIVE

## One UI and one backend

`frontend/` remains the only ARKALI user-interface source. Tauri 2 hosts the
same Vite production output used by the browser; there is no desktop copy of
the Command Center, Project Registry, Workflow Studio, navigation, state, or
API contract.

The desktop host does not rewrite FastAPI in Rust. It starts the existing
`scripts/run_command_center.py` composition root, packaged as a Windows
sidecar for the production bundle. Development falls back to the repository
virtual environment. Both paths run the same application factory, Alembic
migrations, PDP/PEP, Project Registry, workflow authorities, and fixed
loopback API. The database is stored below Tauri's per-user app-data directory.

Lifecycle is deliberately small: accept an already-running process only when
the exact ARKALI health shape is returned, reject a conflicting listener,
start one fixed executable with fixed loopback arguments, wait for health,
and remove an ownership sentinel for graceful shutdown. The single-instance
plugin focuses the existing main window instead of starting another owner.

## Native and network boundary

The frontend has no Tauri commands or permissions. No shell, filesystem,
opener, credential, process, or store plugin is installed. Rust exposes no
`#[tauri::command]` and accepts neither frontend arguments nor environment
overrides for process selection. The only process target is the packaged
ARKALI sidecar (or the fixed development Python/launcher pair).

The CSP permits only the Tauri origin and fixed `127.0.0.1:8000` API. FastAPI
accepts only `http://tauri.localhost` as the desktop CORS origin. Existing
PDP/PEP and Computer-Use authority remain inside the existing backend and are
not bypassed by a native bridge.

## Build and paths

The Tauri production build performs the existing frontend production build,
packages the existing Python composition root with its canonical documents
and migrations, builds the Rust host with the stable MSVC toolchain, and emits
a generic NSIS bundle. Runtime data lives under Tauri app-data; frontend assets
and the backend runtime are bundle resources. Repository-relative paths are a
development fallback only.

The Phase 28 NSIS artifact proves that the desktop candidate can be bundled.
It is not the canonical `ARKALI_Setup.exe`, Recovery Supervisor, deployment,
upgrade, or recovery contract assigned to Phase 29.

## Conditional applicability and limitations

ERR-005 records the Phase-28-only interpretation of ARK-REQ-0180 Appendix A as
`capability.runtime_requirements.local_executable == true`. The canonical
schema represents that nested field, but no shipping capability sets it true;
ARK-REQ-0180 is therefore NOT_APPLICABLE in this candidate.

DEF-009 remains OPEN. Desktop hosting adds no goal-to-running-product loop,
generated-product preview, fake generation progress, external provider, or
external AI dependency.
