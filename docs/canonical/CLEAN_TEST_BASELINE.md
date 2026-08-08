# ARKALI GENESIS v2 — CANONICAL WINDOWS CLEAN-TEST BASELINE DEFINITION (PHASE 0B)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1
**Canonical basis:** Build Protocol §Phase 0B — "canonical Windows clean-test baseline definition"; Master Specification §Real Execution Levels; Verification Contract §Clean installation.

## Scope boundary

| Obligation | Owner phase | Delivered here |
|---|---|---|
| Baseline **definition**: edition, absent-tooling list, snapshot/reset procedure, verification probe, evidence fields | **Phase 0B** | **yes — this document** |
| Baseline **image**: the actual VM and snapshot | Phase 36 (acceptance environment) | no — infrastructure asset (DEF-005) |

This is an acceptance-test environment requirement. **It is not imposed on end users**, who install on whatever Windows they have.

## 1. Baseline host definition

| Property | Value |
|---|---|
| OS | Windows 11 Pro, 64-bit |
| Build | pinned per release; exact build number recorded in evidence |
| Provisioning | clean OS install, then snapshot — never a developer machine |
| State | reverted to snapshot immediately before **each** canonical L3 run |
| Network | outbound permitted (installer may fetch); recorded in evidence |
| User | standard non-elevated account; elevation only where the installer legitimately requires it |

Windows 11 Pro is specified because TRUST-3/TRUST-4 isolation backends (`windows_sandbox`, `hyperv_container`) require Pro or Enterprise. A Home baseline would report those capabilities `UNSUPPORTED` and could not exercise the full isolation matrix.

## 2. Absent-tooling list (verified before installation)

The following must be **absent** from the baseline. Presence invalidates the run.

| # | Must be absent | Probe |
|---|---|---|
| 1 | Python (any version) | `python`, `py`, `python3` not resolvable; no `%LOCALAPPDATA%\Programs\Python` |
| 2 | Node.js / npm | `node`, `npm` not resolvable |
| 3 | Rust / Cargo | `cargo`, `rustc` not resolvable |
| 4 | Git | `git` not resolvable |
| 5 | MSVC build tools / Visual Studio | no `vcvarsall.bat`; no VS installation registry key |
| 6 | Prior ARKALI runtime, data or registry entries | install dir, `%APPDATA%\ARKALI`, `%LOCALAPPDATA%\ARKALI` absent |
| 7 | Any ARKALI-related PATH entry | PATH scan clean |

The list is a **minimum**. It exists to make the bundled-runtime claim testable: with Python and Node absent, an installer that does not genuinely bundle its runtime fails immediately rather than silently borrowing developer tooling.

## 3. Reset and run procedure

1. Revert VM to the named snapshot.
2. Run the absent-tooling probe. Any item present ⇒ run is **INVALID** (not FAIL) — the environment is wrong, and the result carries no verification meaning.
3. Record baseline identity: OS edition, build number, snapshot ID, probe output hash, timestamp.
4. Transfer only the packaged release artifact plus its checksum. Nothing else crosses into the VM.
5. Execute the canonical clean-installation journey (§4).
6. Export evidence out of the VM; never reuse the dirtied VM for a second canonical run.

## 4. Canonical clean-installation journey

install → first run → diagnostics → setup → configure provider or local model → create project → generate product → observe → acceptance → use product → restart / persistence → backup / restore.

Each step records outcome and duration. A step that cannot execute records an honest state with its reason; it is never skipped silently.

## 5. Required evidence fields per L3 run

`baseline_os_edition` · `baseline_build_number` · `snapshot_id` · `absent_tooling_probe_result` · `probe_output_hash` · `release_artifact_hash` · `run_timestamp` · `per_step_outcomes` · `installer_exit_code` · `first_run_diagnostics_output`.

An L3 run whose evidence lacks `snapshot_id` or `absent_tooling_probe_result` is rejected — it cannot be distinguished from a developer-machine run.

## 6. Reproducibility requirement

Two consecutive runs from the same snapshot with the same release artifact must produce equivalent install outcomes. Divergence indicates hidden environment dependence and is a finding, not noise.

## 7. Known environmental risk (recorded, not resolved here)

An unsigned `ARKALI_Setup.exe` will trigger SmartScreen on a genuinely clean baseline. This is a real installation obstacle that a developer-machine run would have concealed. Code signing is not currently a canonical requirement; the risk is carried as a MEDIUM finding and must be resolved before Phase 36 rather than worked around by disabling SmartScreen — disabling it would invalidate the baseline.
