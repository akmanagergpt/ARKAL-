# ARKALI GENESIS v2 — SECURITY ARCHITECTURE (PHASE 0A)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1

---

## 1. Policy Authority / PDP / PEP architecture

```
  caller (API | UI | agent | workflow | plugin | computer-use | sandbox)
      |
      v
  PEP  (Policy Enforcement Point — at every call site, no bypass path)
      |
      v
  PDP  (Policy Decision Point — pure, deterministic, side-effect free)
      |  reads
      +--> Policy Authority   (rules, trust tiers, Local-Only mode)
      +--> control.isolation  (backend property availability)
      +--> control.registry.* (subject/target identity)
      |
      v
  decision: AUTO | ASK_USER | DENY   -> audit record (always, including AUTO)
```

**Rules.**
- The PDP is deterministic and pure. Same inputs ⇒ same decision. No AI participates in a policy decision.
- There is exactly one PDP. No component may compute its own decision or cache one.
- Every decision is audited, including AUTO.
- A decision that cannot be resolved is DENY (fail-closed).
- `control.policy` is Protected Core; changing it is HUMAN GATE 4.

## 2. Computer-Use operation classes

Fourteen canonical classes. Any action not mappable to a class is DENY.

| Class | TRUST-0/1 | TRUST-2 | TRUST-3/4 | Fixed rule |
|---|---|---|---|---|
| `READ_FILE` | AUTO (scoped) | AUTO (workspace) | AUTO (workspace) | — |
| `WRITE_WORKSPACE_FILE` | AUTO | AUTO | AUTO | — |
| `WRITE_STABLE_FILE` | DENY | DENY | DENY | **DENY for every actor, always** |
| `ROLLBACK_STABLE` | DENY | DENY | DENY | **Recovery Supervisor only** |
| `RUN_PROCESS` | AUTO | AUTO (confined) | ASK_USER | — |
| `TERMINATE_PROCESS` | AUTO (own) | AUTO (own) | AUTO (own) | never cross-boundary |
| `BROWSER_LOCAL` | AUTO | AUTO | AUTO | loopback only |
| `BROWSER_EXTERNAL` | ASK_USER | ASK_USER | DENY | DENY in Local-Only |
| `NETWORK_EXTERNAL` | ASK_USER | ASK_USER | DENY | DENY in Local-Only |
| `INSTALL_DEPENDENCY` | AUTO (locked manifest) | AUTO (locked, confined) | ASK_USER | lockfile-bound only |
| `INSTALL_SYSTEM_SOFTWARE` | ASK_USER | DENY | DENY | **never AUTO** |
| `CHANGE_SYSTEM_CONFIGURATION` | ASK_USER | DENY | DENY | **never AUTO** |
| `ACCESS_SECRET` | AUTO only within pre-authorized scope | DENY | DENY | **never AUTO outside scope** |
| `APPLY_MIGRATION` | ASK_USER (dev data) | DENY | DENY | **HUMAN GATE 6 on real/stable data** |

Plugin manifests declare permissions using these same classes. There is no separate plugin permission vocabulary.

## 3. TRUST-tier security property matrix

| Tier | Content | Required properties | Human approval |
|---|---|---|---|
| TRUST-0 | deterministic internal code | none (in-process) | no |
| TRUST-1 | ARKALI-maintained extensions | `FS_CONFINEMENT`, `PROCESS_CONTAINMENT`, `RESOURCE_LIMITS` | no |
| TRUST-2 | generated candidate code | TRUST-1 + `NET_EGRESS_CONTROL` + `CREDENTIAL_ISOLATION` | no; external egress ASK_USER |
| TRUST-3 | imported / untrusted projects | TRUST-2 + `KERNEL_ISOLATION`; static inspection before any execution | yes, before first execution |
| TRUST-4 | internet-sourced executable content | TRUST-3 + `DISPOSABILITY` | yes, per execution |

Property definitions are canonical in the Master Specification and are not restated here.

## 4. Isolation Backend architecture

```
  capability request (tier T)
      |
      v
  control.isolation.resolve(T)
      |  required_properties(T)  -> set R
      |  available_backends      -> each declares provided property set
      |  find composition C where union(provides(C)) >= R
      |
      +-- composition found  -> execution.sandbox launches under C
      +-- none found         -> capability = UNSUPPORTED, execution = DENY
```

| Backend | Provides |
|---|---|
| `job_object` | `PROCESS_CONTAINMENT`, `RESOURCE_LIMITS` |
| `restricted_token` | `FS_CONFINEMENT` (with ACL), partial `CREDENTIAL_ISOLATION` |
| `workspace_acl` | `FS_CONFINEMENT` |
| `wfp_egress` | `NET_EGRESS_CONTROL` |
| `vault_detach` | `CREDENTIAL_ISOLATION` |
| `windows_sandbox` | all of the above + `KERNEL_ISOLATION` + `DISPOSABILITY` |
| `hyperv_container` | all of the above + `KERNEL_ISOLATION` |

**Rules.**
- Backends compose; a tier is satisfied by the union of a composition's properties.
- Availability is probed once at Phase 4 and recorded in the Capability Graph as a reference.
- If a required property cannot be provided, the capability is UNSUPPORTED and execution is DENY. **A tier is never silently downgraded and a missing property is never substituted or defaulted.**
- ARKALI remains fully operational for capabilities whose requirements are still satisfiable. Losing `windows_sandbox` and `hyperv_container` disables TRUST-3/4 capabilities only (Import/Rescue, internet-sourced execution); the factory, TRUST-2 generation and all verification continue.
- The Isolation Backend registry is Protected Core; adding or changing a backend is HUMAN GATE 4.

## 5. Protected Core architecture

Membership declared in `AUTHORITY_MAP.yaml` (`protected_core: true`):

`control.policy` · `control.isolation` · `control.architecture` (canonical authority definitions, budgets) · `evidence.audit` (evidence integrity) · `acceptance.engine` (acceptance contracts + Phase Gate Checker) · `lifecycle.release` (stable-promotion machinery) · `lifecycle.recovery` (Recovery Supervisor) · Secret Vault (within `control.policy`).

**Modification path.** Protected Core changes only through the Stable Core candidate lifecycle under the stronger verification profile — security review, adversarial review, full regression — and require HUMAN GATE 2. No implementing actor may add to, remove from or reinterpret membership. This is what makes acceptance independence structural rather than procedural: an actor cannot weaken the contracts it is measured against.

## 6. Secret Vault architecture

```
  human operator ---(explicit provisioning, ASK_USER)---> Secret Vault
                                                             | OS key protection
                                                             | (Windows DPAPI or equivalent)
                                                             v
  consumer --request scope--> Permission Broker --scoped, revocable reference--> consumer
```

- Secrets enter **only** through explicit human-initiated provisioning. No agent, workflow, plugin, generated product or computer-use worker may write, read or export a raw secret value.
- Consumers receive scoped, brokered, revocable references. Raw values never cross a trust boundary, never enter a context package, log, prompt, export or release artifact.
- `CREDENTIAL_ISOLATION` makes the vault unreachable from TRUST-2 and above.
- If no OS key-protection facility is available, secret-dependent capabilities are UNSUPPORTED rather than stored unprotected.

## 7. Local-Only mode

A canonical policy mode. When enabled the PDP returns DENY for all outbound egress on every path — provider, research, plugin/connector, external browser, agent, workflow — from every trust tier. Loopback remains permitted so local build, test and browser verification continue. Enabling or disabling it is HUMAN GATE 4. No capability may silently degrade to a cloud path while it is enabled; with only cloud providers configured, Golden Factory Acceptance reports NOT_CONFIGURED, never a silent cloud call.
