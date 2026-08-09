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
  CreateProjectRequest,
  CreateRevisionRequest,
  HealthResponse,
  LifecycleMachineResponse,
  ProjectDetailResponse,
  ProjectListResponse,
  TransitionRequest,
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
    options: { params?: Record<string, string>; body?: unknown } = {},
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
      });
    } catch (cause) {
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
}

/** The client the application runs against. Configured by Vite at build time. */
export const apiClient = new ArkaliApiClient({
  baseUrl: import.meta.env.VITE_ARKALI_API_BASE_URL ?? '',
});
