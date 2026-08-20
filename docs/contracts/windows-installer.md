# Windows Installer Integration

Phase 29 produces the canonical Windows artifact `ARKALI_Setup.exe` from the
Phase 28 Tauri/NSIS chain. The artifact contains the existing React/Vite build
and the existing FastAPI composition root; it does not define another UI,
backend, Project Registry, workflow authority, policy authority, or rollback
authority.

## Artifact and lifecycle

- Format: NSIS, x86-64 Windows, `currentUser` install mode.
- Identity: `dev.arkali.command-center`.
- Canonical output: `artifacts/installer/ARKALI_Setup.exe`.
- Provenance: version, source commit, size, architecture, install mode, and
  SHA-256 are frozen beside the ignored binary.
- Upgrade: a higher-version Tauri config overlay changes the bundle version
  only. The same app identifier and app-data directory preserve the existing
  SQLite Project Registry.
- Uninstall removes installed application files. The user-owned app-data
  database is retained, so reinstall can reopen the same projects.

## Recovery authority

An installer health failure is submitted through
`scripts/installer_recovery_composition.py` to the already accepted C-32
`RecoverySupervisor`. The composition root adapts the existing PDP/PEP and
C-14/C-15 evidence services. Only C-32 can authorize and perform the Stable
pointer rollback. The acceptance runner maps C-32's selected content address
to an already verified installer and reruns that exact artifact.

The desktop frontend receives no installer, filesystem, process, shell, or
rollback command. Both acceptance runners live outside shipping packages and
use fixed ignored paths below `artifacts/`.

## Explicit exclusions

No Windows code-signing identity or trusted offline-update signing key is
configured. Therefore the installer has SHA-256 provenance but is not claimed
to satisfy optional ARK-REQ-0181's signed offline-update-bundle capability.
No deployment service, auto-updater, second Recovery Supervisor, migration
authority, product generation, or live preview is built. DEF-009 remains open.
