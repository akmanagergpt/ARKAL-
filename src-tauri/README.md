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
