# Release and installer infrastructure root

Phase 1 establishes the root only. No installer, manifest, signing
configuration or packaging script is created.

| Content | Phase | Authority |
|---|---|---|
| Release manifest + SBOM (C-31) | 26 | `lifecycle.release` |
| Windows installer `ARKALI_Setup.exe` | 29 | `lifecycle.release` |
| Recovery Supervisor integration | 29 | `lifecycle.recovery` |
| Clean-environment acceptance run | 36 | `lifecycle.release` |

The canonical clean-test baseline that the installer must pass is already
accepted: `docs/canonical/CLEAN_TEST_BASELINE.md`.

Known carried risk (MEDIUM): an unsigned installer will trigger SmartScreen on a
genuinely clean baseline. Code signing is not currently a canonical requirement;
the risk must be resolved before Phase 36 rather than by disabling SmartScreen,
which would invalidate the baseline.
