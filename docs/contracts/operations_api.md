# Operations + Hardware Intelligence — derived contract (C-34, Phase 25)

**Owner:** `surfaces.operations` (telemetry, Computer-Use authorization,
Source Export/AI Review Bundle — Packages 1, 2/3/4/6); `control.policy`
(the additive `decide_computer_use` PDP method — Package 2);
`surfaces.command` (the HTTP delivery surface — Package 7)
**Kind:** owning authorities (read-only) + Command Center HTTP
**Confinement:** ADDITIVE (per `CONTRACT_INVENTORY.md`'s own row)
**Version:** 1.0.0

This document records the executable Phase 25 contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0168`, `0169`, `0170`, `0218`, `0355`,
`0356`, `0357`, `0395`), `docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md`
section "Operations / Computer Use / Source Export",
`docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md` section
"Operations", `docs/canonical/AUTHORITY_MAP.yaml`'s `surfaces.operations`
declaration, and `docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md` row 25
(no human gate). It does not replace those authorities.

## 0. Scope of this revision

Seven atomic packages, no new state machine, PDP, PEP, policy authority or
operation class minted (`STATE_MACHINES.md` stays at twelve; the fourteen
Computer-Use operation classes were already declared in `AUTHORITY_MAP.yaml`
since Phase 4/10):

1. `runtime_telemetry.py`/`hardware_telemetry.py`/`storage_telemetry.py`/
   `telemetry.py` — real job/workflow/hardware/storage observability
   (`ARK-REQ-0168`), honest `NOT_CONFIGURED` for providers/agents/workers
   since no live registry or scheduler loop exists on this host.
2. `computer_use.py`/`computer_use_contracts.py` + `PolicyDecisionPoint.
   decide_computer_use` (additive, Protected Core) — the real PDP composed
   for all fourteen Computer-Use classes (`ARK-REQ-0170`).
3. `process_boundary.py`/`file_boundary.py`/`browser_boundary.py` —
   permission-aware terminal/file/browser execution, gated by Package 2,
   never bypassed.
4. `test_operations_computer_use_adversarial.py` — negative/adversarial
   proofs: no direct Stable/live mutation, no shadow execution path, `ASK_
   USER` never conflated with permission, no fact can override a fixed
   `DENY`/`ASK_USER` rule.
5. `source_export.py`/`ai_review_bundle.py` + `control.policy.
   secret_reference.redact_raw_secrets` (additive, Protected Core) —
   real, secret-redacted Source Intelligence Export and AI Review Bundle
   (`ARK-REQ-0169`, `0357`).
6. `test_no_fabricated_operational_evidence.py` (`ARK-REQ-0218`) +
   `conditional_dimensions.py` (`ARK-REQ-0356`, `0395`) — a structural proof
   that providers/agents/workers can never be fabricated, and real
   applicability evaluation for the two CONDITIONAL dimensions (both
   honestly `NOT_APPLICABLE` on this host today).
7. `surfaces/command/operations.py` — the real Command Center HTTP surface,
   composing `surfaces.operations` via a new declared same-layer sibling
   edge; the composed journey, this contract document, the C-17 report and
   traceability record.

**Not implemented or claimed by this revision:** any live entrypoint that
takes a natural-language goal and produces a generated product (`DEF-009`,
tracked separately and permanently, explicitly out of this phase's scope,
not silently absorbed here); raw process/file/browser execution exposed over
HTTP (a deliberate, documented scope boundary — §3 explains why); a live
scheduler/worker pool (Phase 8's own honestly-recorded absence); a live
provider registry or agent runtime; a frontend increment (no Phase 25
requirement carries `e2e` evidence, so none is owed — the identical
reasoning Phase 7 Package 4 recorded for `ARK-REQ-0027`).

## 1. Real-time telemetry (`surfaces.operations`, `ARK-REQ-0168`/`0355`)

| Dimension | Source | State on this host |
|---|---|---|
| `jobs_active`/`jobs_queued`/`jobs_stuck` | `execution.durable.JobStore.list_by_state` (additive), `JobRecovery.heartbeat_stale` (unmodified) | Real, live |
| `workflows_active` | `execution.workflow.WorkflowExecutor.list_by_state` (additive) | Real, live |
| `providers`/`agents`/`workers` | Honest absence facts | `NOT_CONFIGURED` — no live registry, agent runtime or scheduler loop exists anywhere in this repository (Phase 16/22/8's own acceptance records; DEF-009) |
| `cpu_logical_cores`/`ram_total_bytes`/`gpu_present` | `engineering.localai.host_probe` (reused unmodified, via a structural `Protocol`) | Real, live |
| `disk_free_bytes`/`network_reachable` | New, read-only probes (`shutil.disk_usage`, local interface enumeration — no outbound call) | Real, live |
| `database_reachable`/`database_size_bytes` | `kernel.persistence.backup.integrity_check`/`engine.py.is_sqlite` (reused unmodified) | Real, live |

Two additive read-only methods were needed and added, mirroring each
store's own existing `.get`-style shape: `JobStore.list_by_state`,
`WorkflowExecutor.list_by_state`. Neither store previously exposed a
listing query — both were single-record lookups only.

**Every dimension is `HonestState`-typed** (`kernel.contracts.honest_state`,
reused unmodified) — `PASS` only when a real value was genuinely observed,
`NOT_CONFIGURED`/`NOT_APPLICABLE` otherwise, never a fabricated success
(§6).

## 2. Computer-Use operation authorization (`control.policy`, `surfaces.operations`, `ARK-REQ-0170`)

`PolicyDecisionPoint.decide_computer_use` (Protected Core, additive) is
primitives-in/primitives-out — the identical shape `decide_network_egress`
(Phase 21) already established — because `control.policy.pep`/
`.policy_contract` were both already at their 15-of-15 fan-in ceiling.
`authorize_computer_use_action` (`surfaces.operations.computer_use`)
composes it for the real `computer_use_worker` actor — a label
`AUTHORITY_MAP.yaml`'s `stable_mutation.prohibited_actors` already named
before this phase existed, not invented here.

No new operation class, PDP, PEP or trust-tier matrix is created. The
fourteen classes and `SECURITY_ARCHITECTURE.md` §2's own resolution table
are parsed live from `AUTHORITY_MAP.yaml` exactly as every other execution
surface already does; `decide_computer_use` is proven never to diverge from
the general `decide()` entry point across all fourteen classes and five
trust tiers (`test_pdp_computer_use_decisions.py`).

## 3. Permission-aware execution boundaries (`surfaces.operations`, `ARK-REQ-0170`)

`process_boundary.py`/`file_boundary.py`/`browser_boundary.py` never
execute before Package 2's PDP decision `permits_execution`. `RUN_PROCESS`/
`INSTALL_DEPENDENCY` run a real, argument-vector-only subprocess
(`shell=False` always); `TERMINATE_PROCESS` accepts only a real
`subprocess.Popen` handle the caller already holds — there is no
PID-by-number entry point, so "own process only, never cross-boundary" is
enforced structurally, not only by policy. File access is confined to a
caller-supplied root by the identical two-step relative-path +
post-`resolve()` check `engineering.candidate.workspace.CandidateWorkspace`
already established (a parallel confinement, not a reuse of that class —
its own chain into `kernel.contracts` is already at
`max_orchestration_depth`). Browser authorization is real; launch is
honestly `NOT_CONFIGURED` — no automation driver is declared in
`backend/pyproject.toml` on this host.

**None of these three modules is reachable over HTTP** (§7) — a deliberate
scope boundary: a network-reachable endpoint that ran an arbitrary
caller-supplied command would be an unreviewed remote-execution surface
regardless of how tightly the PDP gates the operation *class*, since the
PDP has no opinion on a command's *content*.

## 4. Negative / adversarial proofs

`test_operations_computer_use_adversarial.py` proves, by AST scan against
the real shipping source: no `surfaces.operations` module imports
`lifecycle.release`/`lifecycle.recovery` or names `StableRevisionPointer`'s
own `.promote`/`.rollback_to` methods; only `process_boundary.py` calls
`subprocess.run`/`Popen` (the one named, verified exception —
`hardware_telemetry.py`'s own real, read-only `nvidia-smi --query-gpu`
diagnostic probe, proven to carry no mutating flag); every one of the five
gated execution functions calls `authorize_computer_use_action` in its own
body; `ASK_USER` is never conflated with `AUTO`; a crafted `facts` dict with
every tri-state fact forced `True` still cannot resolve `AUTO` for any of
the four never-`AUTO` classes at any trust tier; no shadow operation-class
table exists anywhere in the package.

## 5. Source Intelligence Export + AI Review Bundle (`surfaces.operations`, `ARK-REQ-0169`/`0357`)

`source_export.py` is a real, PDP-gated (`READ_FILE`) file-tree walk with
real content, secrets redacted by `control.policy.secret_reference.
redact_raw_secrets` (Protected Core, additive) — the same `_RAW_SECRET_
SHAPES` pattern `assert_no_raw_secret` already enforces on every evidence/
log/prompt path in this repository, reused for masking rather than
refusal, never a second regex. Confinement mirrors `file_boundary.py`'s own
two-step check. `ai_review_bundle.py` composes architecture (the real,
unmodified `control.architecture.GateRunner`), contracts/issues/evidence
(real path/size/count references to the canonical documents that already
own those facts) and tree/source into one bundle. Reading the tool's own
canonical documents is not a governed Computer-Use operation, matching
every phase's own acceptance tooling; only the target source tree read
goes through the real PDP.

## 6. No fabricated operational evidence (`ARK-REQ-0218`) + CONDITIONAL dimensions (`ARK-REQ-0356`/`0395`)

`test_no_fabricated_operational_evidence.py` proves structurally, not by
convention, that `runtime_telemetry.py`'s `providers`/`agents`/`workers`
keyword arguments can only ever be constructed via `DimensionReading.
not_configured`, never `.real` — the only constructor that carries
`HonestState.PASS` and a number — with a negative control proving the
assertion shape genuinely catches a fabricated reading.

`conditional_dimensions.py` evaluates both remaining CONDITIONAL
dimensions' real applicability predicates from `REQUIREMENT_REGISTER.md`,
never treating CONDITIONAL as "skip": `ARK-REQ-0356` (GPU/VRAM/cost/token)
reads Package 1's own real `gpu_present` result and honestly reports
`cost`/`token_usage` `NOT_APPLICABLE` while no provider is configured on
this host; `ARK-REQ-0395` (quality/latency) composes `engineering.
knowledge`'s real, unmodified `VerifiedOutcome`/`aggregate` (`INT`, no
persisted table) and honestly reports `NOT_APPLICABLE` while no live
pipeline populates any outcome and no live execution loop exists (`DEF-009`)
to probe latency — proven to flip to `PASS` the moment a real outcome is
genuinely supplied.

## 7. The Command Center HTTP surface (`surfaces.command`)

`surfaces/command/operations.py` exposes `GET /api/operations/snapshot`,
`/conditional/hardware-cost`, `/conditional/quality-latency`,
`/architecture`, and `POST /api/operations/computer-use/authorize` —
`BACKEND_ONLY` (no Phase 25 requirement carries `e2e` evidence). Two real,
measured `max_orchestration_depth`/`max_public_surface_per_context`
violations were found by running the gate after declaring the new
`surfaces.command -> surfaces.operations` sibling edge, and repaired by
decomposition: `HostFactsSource`/`JobSource`/`HeartbeatSource` structural
`Protocol`s (mirroring `WorkflowActivitySource`'s own established shape)
replace what would otherwise have been direct `engineering.localai`/
`execution.durable` imports extending an already-at-ceiling chain; the two
new `surfaces.command` symbols were kept private, the identical pattern
Phase 19/23/24 each already used for the same budget shape.

**Verified against a real, live server** (`scripts/run_command_center.py`,
not `TestClient` alone): every route returned this real host's genuine
CPU/RAM/disk/network/GPU facts, a real SQLite integrity check, 8/8
architecture gates passing live, and correct `AUTO`/`ASK_USER` Computer-Use
decisions matching `SECURITY_ARCHITECTURE.md` §2's own table exactly.

## 8. What is explicitly not claimed

- **No live goal-to-product generation pipeline.** Tracked separately and
  permanently as `DEF-009` — a real, measured gap this phase does not close
  and does not silently absorb.
- **No raw execution exposed over HTTP.** `process_boundary.py`/
  `file_boundary.py`/`browser_boundary.py` remain library capabilities for
  a future, human-supervised orchestration surface — a deliberate scope
  boundary (§3), not an oversight.
- **No live provider registry, agent runtime or worker pool.** All three
  are honestly `NOT_CONFIGURED`, never fabricated (§1, §6).
- **No live browser automation.** `browser_boundary.py`'s authorization is
  real; its launch step is honestly `NOT_CONFIGURED` — no driver dependency
  is declared on this host.
- **No new canonical state machine, PDP, PEP, policy authority or operation
  class.** `STATE_MACHINES.md` still declares exactly twelve; the fourteen
  Computer-Use classes were already declared since Phase 4/10.
- **No frontend increment.** No Phase 25 requirement carries `e2e`
  evidence, so none is owed (Phase 27 consolidates navigation later, per
  MS's own rule).
