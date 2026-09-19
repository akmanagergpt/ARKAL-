# ARKALI desktop shell (Tauri 2.x)

This is a native host for the one Command Center frontend in `../frontend`.
There is no desktop-specific UI tree and no Rust copy of backend behaviour.

The Rust application deliberately registers no Tauri command and grants no
capability permission. Backend lifecycle is introduced separately, through a
fixed composition-root process rather than an arbitrary frontend bridge.

Development and production assets are built by the existing frontend scripts:

```powershell
npm --prefix frontend run tauri -- dev
npm --prefix frontend run tauri -- build --no-bundle
```

Phase 29 owns the final `ARKALI_Setup.exe` and Recovery Supervisor integration.

The local developer desktop shortcut may point to
`scripts/launch_desktop_latest.ps1`. It compares the current Git HEAD with the
last successful local release build and runs `tauri build --no-bundle` before
opening the app when they differ. It refuses to open a stale build if sources
are uncommitted, the old app is still running, or rebuilding fails. This is a
local checkout convenience, not a production update or installer mechanism.
