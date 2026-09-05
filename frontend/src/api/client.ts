/**
 * The single API boundary between the Command Center frontend and
 * `surfaces.command`.
 *
 * ONE BOUNDARY, NOT MANY. `fetch` is called here and nowhere else in the
 * application; a control parses the source tree and fails if a component
 * acquires its own network call. That is not style — a component that fetches
 * directly is a component that can quietly adopt a different contract.
 *
 * NO AUTHORITY LIVES HERE. This module transports requests and narrows
 * responses. It decides no lifecycle legality, evaluates no policy and holds no
 * copy of registry state. A refusal is surfaced exactly as the backend phrased
 * it, because the backend is the only party entitled to phrase one.
 */

import type {
  ApproveExecutionRequest,
  _ChangePromotionResponse,
  CreateProjectRequest,
  CreateRevisionRequest,
  _FactoryGoalRequest,
  FactoryHistorySnapshot,
  _FactoryIntakeResponse,
  HealthResponse,
  _JobCheckpointResponse,
  JobReferenceResponse,
  LifecycleMachineResponse,
  OperationsSnapshot,
  ProjectDetailResponse,
  ProjectListResponse,
  PublishWorkflowRevisionRequest,
  StartExecutionRequest,
  _StartChangeRequest,
  TransitionRequest,
  WorkflowExecutionDetailResponse,
  WorkflowRevisionDetailResponse,
  WorkflowRevisionListResponse,
} from './contracts';

/**
 * Every route this slice speaks to, declared as data.
 *
 * Path templates are written exactly as the backend declares them, so
 * `test_contract_drift.py` can compare this table against the OpenAPI document.
 * A renamed or removed route fails that control.
 */
export const ENDPOINTS = {
  health: { method: 'GET', path: '/api/health' },
  lifecycle: { method: 'GET', path: '/api/lifecycle/project' },
  listProjects: { method: 'GET', path: '/api/projects' },
  createProject: { method: 'POST', path: '/api/projects' },
  getProject: { method: 'GET', path: '/api/projects/{project_id}' },
  transitionProject: { method: 'POST', path: '/api/projects/{project_id}/transitions' },
  createRevision: { method: 'POST', path: '/api/projects/{project_id}/revisions' },
  publishWorkflowRevision: { method: 'POST', path: '/api/workflows/{workflow_id}/revisions' },
  getLatestWorkflowRevision: { method: 'GET', path: '/api/workflows/{workflow_id}' },
  listWorkflowRevisions: { method: 'GET', path: '/api/workflows/{workflow_id}/revisions' },
  getWorkflowRevision: {
    method: 'GET',
    path: '/api/workflows/{workflow_id}/revisions/{revision_number}',
  },
  startWorkflowExecution: { method: 'POST', path: '/api/workflows/{workflow_id}/executions' },
  getWorkflowExecution: {
    method: 'GET',
    path: '/api/workflows/{workflow_id}/executions/{execution_id}',
  },
  signalWorkflowExecution: {
    method: 'POST',
    path: '/api/workflows/{workflow_id}/executions/{execution_id}/signal',
  },
  approveWorkflowExecution: {
    method: 'POST',
    path: '/api/workflows/{workflow_id}/executions/{execution_id}/approve',
  },
  operationsSnapshot: { method: 'GET', path: '/api/operations/snapshot' },
  factoryHistory: { method: 'GET', path: '/api/factory/history' },
  submitFactoryGoal: { method: 'POST', path: '/api/factory/goals' },
  startPreview: { method: 'POST', path: '/api/candidates/{candidate_id}/preview' },
  findPreview: { method: 'GET', path: '/api/candidates/{candidate_id}/preview' },
  startProjectPreview: { method: 'POST', path: '/api/projects/{project_id}/preview' },
  findProjectPreview: { method: 'GET', path: '/api/projects/{project_id}/preview' },
  getJob: { method: 'GET', path: '/api/jobs/{job_id}' },
  listJobCheckpoints: { method: 'GET', path: '/api/jobs/{job_id}/checkpoints' },
  cancelJob: { method: 'POST', path: '/api/jobs/{job_id}/cancel' },
  startProjectChange: { method: 'POST', path: '/api/projects/{project_id}/changes' },
  findProjectChange: { method: 'GET', path: '/api/projects/{project_id}/changes' },
  promoteProjectChange: {
    method: 'POST', path: '/api/projects/{project_id}/changes/{job_id}/promote',
  },
  startRestore: {
    method: 'POST', path: '/api/projects/{project_id}/revisions/{revision_id}/restore',
  },
  startRevisionPreview: {
    method: 'POST', path: '/api/projects/{project_id}/revisions/{revision_id}/preview',
  },
  findRevisionPreview: {
    method: 'GET', path: '/api/projects/{project_id}/revisions/{revision_id}/preview',
  },
} as const;

/**
 * A refusal that reached us with the backend's own code and message.
 *
 * Distinct from a transport failure on purpose: a refused operation is an
 * answer, and the interface should say what the answer was rather than
 * reporting that something went wrong.
 */
export class ApiRefusal extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiRefusal';
    this.code = code;
    this.status = status;
  }
}

/** The backend could not be reached, or answered with something unusable. */
export class ApiUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiUnavailable';
  }
}

type Fetch = typeof globalThis.fetch;

function expand(path: string, params: Record<string, string>): string {
  return path.replace(/\{(\w+)\}/g, (_match, key: string) => {
    const value = params[key];
    if (value === undefined) {
      throw new ApiUnavailable(`missing path parameter '${key}'`);
    }
    return encodeURIComponent(value);
  });
}

/**
 * Read a refusal body without trusting its shape.
 *
 * A 4xx whose body is not the documented envelope is still a refusal; it just
 * cannot explain itself, and inventing an explanation would be worse than
 * admitting that.
 */
function refusalFrom(status: number, body: unknown): ApiRefusal {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === 'object') {
    const { code, message } = detail as { code?: unknown; message?: unknown };
    if (typeof code === 'string' && typeof message === 'string') {
      return new ApiRefusal(status, code, message);
    }
  }
  return new ApiRefusal(status, 'UNSPECIFIED', `The request was refused (${status}).`);
}

export class ArkaliApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: Fetch;

  constructor(options: { baseUrl?: string; fetchImpl?: Fetch } = {}) {
    this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  private async request<T>(
    endpoint: { readonly method: string; readonly path: string },
    options: { params?: Record<string, string>; body?: unknown; signal?: AbortSignal } = {},
  ): Promise<T> {
    const url = this.baseUrl + expand(endpoint.path, options.params ?? {});
    let response: Response;
    try {
      response = await this.fetchImpl(url, {
        method: endpoint.method,
        headers:
          options.body === undefined
            ? { Accept: 'application/json' }
            : { Accept: 'application/json', 'Content-Type': 'application/json' },
        ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      });
    } catch (cause) {
      if (cause instanceof Error && cause.name === 'AbortError') {
        throw cause;
      }
      throw new ApiUnavailable(
        cause instanceof Error
          ? `The Command Center API is unreachable: ${cause.message}`
          : 'The Command Center API is unreachable.',
      );
    }

    let parsed: unknown = null;
    const text = await response.text();
    if (text.length > 0) {
      try {
        parsed = JSON.parse(text) as unknown;
      } catch {
        throw new ApiUnavailable('The Command Center API returned a malformed response.');
      }
    }

    if (!response.ok) {
      if (response.status >= 500) {
        throw new ApiUnavailable(
          `The Command Center API failed (${response.status}).`,
        );
      }
      throw refusalFrom(response.status, parsed);
    }
    return parsed as T;
  }

  health(): Promise<HealthResponse> {
    return this.request<HealthResponse>(ENDPOINTS.health);
  }

  /** The machine's state vocabulary. Not a permission list — see `contracts.ts`. */
  lifecycleStates(): Promise<LifecycleMachineResponse> {
    return this.request<LifecycleMachineResponse>(ENDPOINTS.lifecycle);
  }

  listProjects(): Promise<ProjectListResponse> {
    return this.request<ProjectListResponse>(ENDPOINTS.listProjects);
  }

  createProject(body: CreateProjectRequest): Promise<ProjectDetailResponse> {
    return this.request<ProjectDetailResponse>(ENDPOINTS.createProject, { body });
  }

  getProject(projectId: string): Promise<ProjectDetailResponse> {
    return this.request<ProjectDetailResponse>(ENDPOINTS.getProject, {
      params: { project_id: projectId },
    });
  }

  /**
   * Request a lifecycle move. Nothing here decides whether it is legal: the
   * Project state machine answers, and an illegal move returns an `ApiRefusal`
   * carrying the machine's own reason.
   */
  transitionProject(
    projectId: string,
    body: TransitionRequest,
  ): Promise<ProjectDetailResponse> {
    return this.request<ProjectDetailResponse>(ENDPOINTS.transitionProject, {
      params: { project_id: projectId },
      body,
    });
  }

  createRevision(
    projectId: string,
    body: CreateRevisionRequest,
  ): Promise<ProjectDetailResponse> {
    return this.request<ProjectDetailResponse>(ENDPOINTS.createRevision, {
      params: { project_id: projectId },
      body,
    });
  }

  /**
   * Publish a declared graph as the next revision. `WorkflowGraphStore`
   * derives the revision number and content hash; neither is sent here.
   */
  publishWorkflowRevision(
    workflowId: string,
    body: PublishWorkflowRevisionRequest,
  ): Promise<WorkflowRevisionDetailResponse> {
    return this.request<WorkflowRevisionDetailResponse>(ENDPOINTS.publishWorkflowRevision, {
      params: { workflow_id: workflowId },
      body,
    });
  }

  getLatestWorkflowRevision(workflowId: string): Promise<WorkflowRevisionDetailResponse> {
    return this.request<WorkflowRevisionDetailResponse>(ENDPOINTS.getLatestWorkflowRevision, {
      params: { workflow_id: workflowId },
    });
  }

  listWorkflowRevisions(workflowId: string): Promise<WorkflowRevisionListResponse> {
    return this.request<WorkflowRevisionListResponse>(ENDPOINTS.listWorkflowRevisions, {
      params: { workflow_id: workflowId },
    });
  }

  getWorkflowRevision(
    workflowId: string,
    revisionNumber: number,
  ): Promise<WorkflowRevisionDetailResponse> {
    return this.request<WorkflowRevisionDetailResponse>(ENDPOINTS.getWorkflowRevision, {
      params: { workflow_id: workflowId, revision_number: String(revisionNumber) },
    });
  }

  /**
   * Start an execution. The backend runs the frontier walk synchronously
   * until it pauses (`WAITING_SIGNAL`/`WAITING_APPROVAL`) or reaches a
   * terminal state, and returns that state plus the evidence so far.
   */
  startWorkflowExecution(
    workflowId: string,
    body: StartExecutionRequest,
  ): Promise<WorkflowExecutionDetailResponse> {
    return this.request<WorkflowExecutionDetailResponse>(ENDPOINTS.startWorkflowExecution, {
      params: { workflow_id: workflowId },
      body,
    });
  }

  getWorkflowExecution(
    workflowId: string,
    executionId: string,
  ): Promise<WorkflowExecutionDetailResponse> {
    return this.request<WorkflowExecutionDetailResponse>(ENDPOINTS.getWorkflowExecution, {
      params: { workflow_id: workflowId, execution_id: executionId },
    });
  }

  signalWorkflowExecution(
    workflowId: string,
    executionId: string,
  ): Promise<WorkflowExecutionDetailResponse> {
    return this.request<WorkflowExecutionDetailResponse>(ENDPOINTS.signalWorkflowExecution, {
      params: { workflow_id: workflowId, execution_id: executionId },
    });
  }

  /**
   * Record a HUMAN APPROVAL decision. Nothing here decides whether it
   * counts: `control.policy.WorkflowApprovalGate` answers, and a stale or
   * disallowed decision returns an `ApiRefusal` carrying its own reason.
   */
  approveWorkflowExecution(
    workflowId: string,
    executionId: string,
    body: ApproveExecutionRequest,
  ): Promise<WorkflowExecutionDetailResponse> {
    return this.request<WorkflowExecutionDetailResponse>(ENDPOINTS.approveWorkflowExecution, {
      params: { workflow_id: workflowId, execution_id: executionId },
      body,
    });
  }

  /**
   * The real-time Operations telemetry snapshot (`ARK-REQ-0396`, D-028).
   * Re-derived by the backend on every call from live authorities — never
   * cached here, never held across renders as if it were still current.
   * `signal` lets a caller (a polling hook, an unmounting component) abort
   * the underlying request rather than merely ignore its result.
   */
  operationsSnapshot(signal?: AbortSignal): Promise<OperationsSnapshot> {
    return this.request<OperationsSnapshot>(
      ENDPOINTS.operationsSnapshot,
      signal === undefined ? {} : { signal },
    );
  }

  /**
   * The real, read-only Phase 30 production history: every `golden-work-*`
   * candidate and campaign the pipeline's own ledgers have recorded.
   * NOT a live orchestrator view and never a trigger — see
   * `FactoryHistorySnapshot`'s own doc comment.
   */
  factoryHistory(signal?: AbortSignal): Promise<FactoryHistorySnapshot> {
    return this.request<FactoryHistorySnapshot>(
      ENDPOINTS.factoryHistory,
      signal === undefined ? {} : { signal },
    );
  }

  /**
   * Submit one real goal to `ProductionFactory.submit_goal`. Always returns
   * `202` with an honest `ProductionIntake` — `governed_stop`, `escalated`
   * or `queued` — never a promise that generation began. This is the same
   * real intake `POST /api/factory/goals` already offers; nothing here
   * re-derives or guesses at a blueprint.
   */
  submitFactoryGoal(body: _FactoryGoalRequest): Promise<_FactoryIntakeResponse> {
    return this.request<_FactoryIntakeResponse>(ENDPOINTS.submitFactoryGoal, { body });
  }

  /**
   * "Uygulamayı Aç" for one candidate — a real, domain-specific intake
   * over C-19, the same shape `submitFactoryGoal` is for goals: the
   * frontend never builds a `(job_type, idempotency_key)` pair itself.
   * Idempotent by the backend's own persisted unique constraint: calling
   * this again for the same candidate (e.g. after a browser refresh)
   * returns the real, already-running job rather than a duplicate.
   */
  startPreview(candidateId: string): Promise<JobReferenceResponse> {
    return this.request<JobReferenceResponse>(ENDPOINTS.startPreview, {
      params: { candidate_id: candidateId },
    });
  }

  /**
   * Whether a real preview job already exists for this candidate, without
   * creating one — `null` if nothing has ever been opened. The whole
   * mechanism `usePreview.ts` uses to rediscover a real preview after a
   * browser refresh: a plain read on mount, never a client-storage guess.
   */
  findPreview(candidateId: string): Promise<JobReferenceResponse | null> {
    return this.request<JobReferenceResponse | null>(ENDPOINTS.findPreview, {
      params: { candidate_id: candidateId },
    });
  }

  /**
   * "Uygulamayı Aç" from Product Detail — the real Managed Product ->
   * accepted candidate bridge (D-029's own follow-on). Resolves through
   * the backend's own canonical chain (`ProjectRegistry` -> `provenance_ref`
   * -> `ArtifactStore` -> `CandidateLedger` eligibility) and submits or
   * recovers the same real preview job the candidate-direct route uses —
   * never a second preview path. Idempotent the same way: a repeated call
   * for a product with an already-active preview rediscovers it; a repeated
   * call after that preview reached a real terminal state starts a genuinely
   * new one.
   */
  startProjectPreview(projectId: string): Promise<JobReferenceResponse> {
    return this.request<JobReferenceResponse>(ENDPOINTS.startProjectPreview, {
      params: { project_id: projectId },
    });
  }

  /**
   * Whether a real preview job already exists for this Managed Product,
   * without creating one — `null` if nothing has ever been opened. The
   * refresh-recovery counterpart to `startProjectPreview`.
   */
  findProjectPreview(projectId: string): Promise<JobReferenceResponse | null> {
    return this.request<JobReferenceResponse | null>(ENDPOINTS.findProjectPreview, {
      params: { project_id: projectId },
    });
  }

  /**
   * The real, current lifecycle state of a durable job — a plain read,
   * never a mutation. Used to poll a real `software_factory.production`
   * job after a `queued` intake result.
   */
  getJob(jobId: string): Promise<JobReferenceResponse> {
    return this.request<JobReferenceResponse>(ENDPOINTS.getJob, {
      params: { job_id: jobId },
    });
  }

  /**
   * Every real checkpoint a worker recorded for a job, oldest first — the
   * real progress evidence this slice derives its progress display from,
   * never a second progress-state store.
   */
  listJobCheckpoints(jobId: string): Promise<_JobCheckpointResponse[]> {
    return this.request<_JobCheckpointResponse[]>(ENDPOINTS.listJobCheckpoints, {
      params: { job_id: jobId },
    });
  }

  /**
   * Request early termination of a real job — Command Center's real
   * "Durdur". Idempotent: cancelling an already-CANCELLED job returns its
   * current reference rather than refusing, the same way the backend
   * route itself treats it.
   */
  cancelJob(jobId: string): Promise<JobReferenceResponse> {
    return this.request<JobReferenceResponse>(ENDPOINTS.cancelJob, {
      params: { job_id: jobId },
    });
  }

  /**
   * "Değişikliği Başlat" (D-030 V1) — a real natural-language Managed
   * Product change request. Idempotent the same way `startProjectPreview`
   * is: a repeated call for a project with an already-active change cycle
   * rediscovers it; a repeated call after the most recent one reached a
   * real terminal state starts a genuinely new cycle.
   */
  startProjectChange(projectId: string, requestText: string): Promise<JobReferenceResponse> {
    const body: _StartChangeRequest = { request_text: requestText };
    return this.request<JobReferenceResponse>(ENDPOINTS.startProjectChange, {
      params: { project_id: projectId }, body,
    });
  }

  /**
   * Whether a real change cycle already exists for this project, without
   * creating one — `null` if nothing has ever been requested. The
   * refresh-recovery counterpart to `startProjectChange`.
   */
  findProjectChange(projectId: string): Promise<JobReferenceResponse | null> {
    return this.request<JobReferenceResponse | null>(ENDPOINTS.findProjectChange, {
      params: { project_id: projectId },
    });
  }

  /**
   * "Kabul Et" — real, synchronous promotion of a ready change proposal
   * into a new `ProjectRevisionRecord`. "Vazgeç" needs no method of its
   * own: it is the existing `cancelJob`, called with the same job id.
   */
  promoteProjectChange(projectId: string, jobId: string): Promise<_ChangePromotionResponse> {
    return this.request<_ChangePromotionResponse>(ENDPOINTS.promoteProjectChange, {
      params: { project_id: projectId, job_id: jobId },
    });
  }

  /**
   * "Bu sürüme geri dön" — a real restore proposal over the SAME
   * `managed_product.change` job/idempotency slot `startProjectChange`
   * uses. `revisionId` is the SOURCE-BASIS revision being restored, never
   * required to be the project's current revision. Idempotent the same
   * way `startProjectChange` is.
   */
  startRestore(projectId: string, revisionId: string): Promise<JobReferenceResponse> {
    return this.request<JobReferenceResponse>(ENDPOINTS.startRestore, {
      params: { project_id: projectId, revision_id: revisionId },
    });
  }

  /**
   * "Önizle" on an explicitly selected historical `Sürüm` — a real,
   * ephemeral preview cycle over exactly that revision's own immutable
   * source, never the project's current revision by default. Idempotent
   * the same way `startProjectPreview` is.
   */
  startRevisionPreview(projectId: string, revisionId: string): Promise<JobReferenceResponse> {
    return this.request<JobReferenceResponse>(ENDPOINTS.startRevisionPreview, {
      params: { project_id: projectId, revision_id: revisionId },
    });
  }

  /**
   * Whether a real historical-preview job already exists for this
   * revision, without creating one — the refresh-recovery counterpart to
   * `startRevisionPreview`.
   */
  findRevisionPreview(projectId: string, revisionId: string): Promise<JobReferenceResponse | null> {
    return this.request<JobReferenceResponse | null>(ENDPOINTS.findRevisionPreview, {
      params: { project_id: projectId, revision_id: revisionId },
    });
  }
}

/** The client the application runs against. Configured by Vite at build time. */
export function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

export const apiClient = new ArkaliApiClient({
  baseUrl:
    import.meta.env.VITE_ARKALI_API_BASE_URL
    ?? (isTauriRuntime() ? 'http://127.0.0.1:8000' : ''),
});
