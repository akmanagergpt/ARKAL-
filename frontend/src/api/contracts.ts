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
