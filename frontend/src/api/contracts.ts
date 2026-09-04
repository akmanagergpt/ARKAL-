/**
 * Transport-contract representations of the Command Center API.
 *
 * THESE ARE NOT A DOMAIN MODEL. Every type below is the shape of a message on
 * the wire, nothing more. `lifecycle_state` is `string`, not a union of the
 * Project machine's states, because narrowing it here would mean this file had
 * decided what the states are — and the Project machine in
 * `control.registry.project` is the only authority that may.
 *
 * NAMES ARE LOAD-BEARING. Each interface name matches a component schema name
 * in the backend's OpenAPI document, and `test_contract_drift.py` compares the
 * two field by field. A backend rename or type change fails that control rather
 * than being discovered at runtime in a browser.
 */

export interface CreateProjectRequest {
  project_id: string;
  name: string;
}

export interface CreateRevisionRequest {
  revision_id: string;
  provenance_ref: string | null;
}

export interface TransitionRequest {
  target: string;
}

export interface RevisionResponse {
  revision_id: string;
  sequence: number;
  created_at: string;
  provenance_ref: string | null;
}

export interface ProjectResponse {
  project_id: string;
  name: string;
  lifecycle_state: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetailResponse {
  project_id: string;
  name: string;
  lifecycle_state: string;
  created_at: string;
  updated_at: string;
  revisions: RevisionResponse[];
}

export interface ProjectListResponse {
  projects: ProjectResponse[];
}

export interface HealthResponse {
  status: string;
  schema_revision: string | null;
}

/**
 * The canonical machine's state vocabulary.
 *
 * `states` is a vocabulary, never a permission set. Which state is reachable
 * from the project's current one is answered by the backend when the move is
 * attempted; a client that filtered this list would have invented a transition
 * relation of its own.
 */
export interface LifecycleMachineResponse {
  machine: string;
  states: string[];
}

/** A refusal the user can act on. Arrives as the `detail` of a 4xx response. */
export interface ErrorResponse {
  code: string;
  message: string;
}

/**
 * C-20 workflow graph shapes (Phase 17).
 *
 * `WorkflowNodeShape`/`WorkflowEdgeShape` are projected field-for-field from
 * `execution.workflow.graph_model`'s value objects. `kind` and
 * `control_construct` are plain strings here, never a union: the canonical
 * vocabulary lives in `GraphVocabulary`, parsed from the VDC, and this file
 * declaring a union would be a second, driftable copy of it. A graph the
 * Studio composes is only ever validated by the backend's `publish` call —
 * the same "offer it, let the backend refuse it" discipline the Project
 * lifecycle picklist already uses.
 */
export interface WorkflowNodeShape {
  node_id: string;
  kind: string;
  control_construct: string | null;
  label: string;
  parameters: Record<string, unknown>;
  position_x: number;
  position_y: number;
}

export interface WorkflowEdgeShape {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  condition: string | null;
}

export interface PublishWorkflowRevisionRequest {
  nodes: WorkflowNodeShape[];
  edges: WorkflowEdgeShape[];
  semver_bump: string;
}

export interface WorkflowRevisionResponse {
  workflow_id: string;
  revision_number: number;
  semver: string;
  revision_hash: string;
  created_at: string;
}

export interface WorkflowRevisionDetailResponse {
  workflow_id: string;
  revision_number: number;
  semver: string;
  revision_hash: string;
  created_at: string;
  nodes: WorkflowNodeShape[];
  edges: WorkflowEdgeShape[];
}

export interface WorkflowRevisionListResponse {
  revisions: WorkflowRevisionResponse[];
}

export interface StartExecutionRequest {
  execution_id: string;
  revision_number: number | null;
}

export interface ApproveExecutionRequest {
  node_id: string;
  actor: string;
  decision: string;
  approved_revision_hash: string;
}

export interface WorkflowNodeExecutionResponse {
  sequence: number;
  node_id: string;
  kind: string;
  control_construct: string | null;
  revision_hash: string;
  outcome: string;
  job_id: string | null;
  recorded_at: string;
}

/**
 * C-34 Operations telemetry shapes (`ARK-REQ-0396`, D-028).
 *
 * `DimensionReading.value` is populated only when `state` is `PASS` — a
 * `NOT_CONFIGURED`/`NOT_APPLICABLE` reading never carries a number, so a
 * component must never mistake "no data" for a real zero. `state` is
 * `string`, not a union of `HonestState`'s members, for the identical
 * reason `lifecycle_state` above is `string`: `kernel.contracts.honest_state`
 * is the sole authority for that vocabulary, and narrowing it here would be
 * a second, driftable copy of it.
 */
export interface DimensionReading {
  dimension: string;
  state: string;
  detail: string;
  value: number | null;
}

export interface RuntimeSnapshot {
  jobs_active: DimensionReading;
  jobs_queued: DimensionReading;
  jobs_stuck: DimensionReading;
  workflows_active: DimensionReading;
  providers: DimensionReading;
  agents: DimensionReading;
  workers: DimensionReading;
}

export interface HardwareSnapshot {
  cpu_logical_cores: DimensionReading;
  ram_total_bytes: DimensionReading;
  disk_free_bytes: DimensionReading;
  network_reachable: DimensionReading;
  gpu_present: DimensionReading;
  vram_total_bytes: DimensionReading;
}

export interface StorageSnapshot {
  database_reachable: DimensionReading;
  database_size_bytes: DimensionReading;
}

export interface OperationsSnapshot {
  runtime: RuntimeSnapshot;
  hardware: HardwareSnapshot;
  storage: StorageSnapshot;
}

/**
 * Read-only Phase 30 production-history shapes.
 *
 * NOT A LIVE ORCHESTRATOR VIEW. This is what the staged-generation
 * pipeline's own CLI-driven runs (`run_staged_generation.py`/
 * `run_golden_acceptance.py`) have already recorded to disk — never a
 * trigger, never a live job. See `factory_history.py`'s own module
 * docstring (DEF-009 remains open; this does not close it).
 */
export interface FactoryCandidateSummary {
  candidate_id: string;
  state: string;
  recorded_at: string;
}

export interface FactoryCampaignAttempt {
  candidate_id: string;
  outcome: string;
  failure_class: string | null;
  fingerprint: string | null;
  elapsed_seconds: number;
  recorded_at: string;
}

export interface FactoryCampaignSummary {
  campaign_id: string;
  max_new_candidates: number;
  max_total_seconds: number;
  max_same_fingerprint_repeats: number;
  consumed_candidates: number;
  consumed_seconds: number;
  status: string;
  attempts: FactoryCampaignAttempt[];
}

export interface FactoryHistorySnapshot {
  candidates: FactoryCandidateSummary[];
  campaigns: FactoryCampaignSummary[];
}

/**
 * The real `POST /api/factory/goals` intake — `ProductionFactory.submit_goal`
 * composed unmodified. `capability_id` is optional; when omitted, the real
 * composition root (`scripts/run_command_center.py`) defaults it to a
 * capability its own real, live Ollama probe found genuinely configured —
 * never a UI-supplied or hard-coded model name. If no real local model is
 * configured on the host running the Command Center, resolution still
 * honestly falls through to `escalated`/`governed_stop`, never a
 * fabricated `queued`. See `NewApplicationIntake.tsx`.
 *
 * NAMED WITH A LEADING UNDERSCORE, MATCHING THE BACKEND. `surfaces.command`
 * has no `max_public_surface_per_context` headroom to spare, so the backend
 * models stay underscore-prefixed (uncounted); FastAPI still publishes each
 * one's literal `__name__` as its OpenAPI component name, and
 * `test_contract_drift.py` compares by that name.
 */
export interface _FactoryGoalRequest {
  request_id: string;
  goal_text: string;
  capability_id: string | null;
}

/** One real, mechanically-derived reason a goal did not fully resolve. */
export interface _UnresolvedQuestionShape {
  subject_index: number | null;
  kind: string;
  detail: string;
}

export interface _FactoryIntakeResponse {
  request_id: string;
  goal_id: string;
  blueprint_id: string;
  state: string;
  selected_tier: string | null;
  unresolved_count: number;
  unresolved: _UnresolvedQuestionShape[];
  durable_job_id: string | null;
}

/**
 * A real C-19 durable job reference — never execution detail (no attempt
 * number, owner, retry count or scheduling metadata; `jobs.py`'s own
 * `JobReferenceResponse` contract refuses all of that). Polled by
 * `NewApplicationIntake.tsx` when a real submission returns a
 * `durable_job_id`.
 */
export interface JobReferenceResponse {
  job_id: string;
  job_type: string;
  idempotency_key: string;
  lifecycle_state: string;
  created_at: string;
}

/**
 * One real checkpoint a worker recorded for a job — the real progress
 * evidence `GET /api/jobs/{job_id}/checkpoints` reads from C-19, never a
 * second progress-state store. `payload` is deliberately untyped beyond
 * `Record<string, unknown>`: its shape is whatever the real worker recorded
 * (ARKALI COMMAND CENTER — DEF-009 FLOW A CONVERGENCE AUTHORIZATION,
 * item 9), read defensively by the UI rather than assumed.
 */
export interface _JobCheckpointResponse {
  sequence: number;
  payload: Record<string, unknown>;
  recorded_at: string;
}

export interface WorkflowExecutionDetailResponse {
  execution_id: string;
  workflow_id: string;
  revision_number: number;
  bound_revision_hash: string;
  lifecycle_state: string;
  pending_approval_node_id: string | null;
  created_at: string;
  updated_at: string;
  evidence: WorkflowNodeExecutionResponse[];
}
