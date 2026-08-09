/**
 * Controlled transport for component tests.
 *
 * THIS IS A TEST BOUNDARY, NOT A DATA SOURCE. Nothing here is importable from
 * `src/`, and a control asserts that production code contains no fixture of its
 * own. The bodies below are copied from real Command Center API responses so a
 * backend shape change is caught by `test_contract_drift.py` rather than being
 * papered over by a fixture that stayed convenient.
 */

import type {
  LifecycleMachineResponse,
  ProjectDetailResponse,
  ProjectListResponse,
} from '@/api/contracts';

export const DRAFT_PROJECT: ProjectDetailResponse = {
  project_id: 'prj-alpha',
  name: 'Alpha Programme',
  lifecycle_state: 'DRAFT',
  created_at: '2026-08-09T09:00:00Z',
  updated_at: '2026-08-09T09:00:00Z',
  revisions: [],
};

export const SPECIFIED_PROJECT: ProjectDetailResponse = {
  ...DRAFT_PROJECT,
  lifecycle_state: 'SPECIFIED',
  updated_at: '2026-08-09T09:05:00Z',
  revisions: [
    {
      revision_id: 'rev-1',
      sequence: 1,
      created_at: '2026-08-09T09:02:00Z',
      provenance_ref: null,
    },
  ],
};

export const LIFECYCLE: LifecycleMachineResponse = {
  machine: 'Project',
  states: ['DRAFT', 'SPECIFIED', 'ACTIVE', 'SUSPENDED', 'ARCHIVED'],
};

export const EMPTY_LIST: ProjectListResponse = { projects: [] };

export function listOf(...projects: ProjectDetailResponse[]): ProjectListResponse {
  return {
    projects: projects.map(({ revisions: _revisions, ...project }) => project),
  };
}

export interface Route {
  readonly status: number;
  readonly body: unknown;
}

export interface Call {
  readonly method: string;
  readonly url: string;
  readonly body: unknown;
}

/**
 * A `fetch` that answers from a routing table and records what was asked.
 *
 * It replaces the network, not the API client: the real `ArkaliApiClient`
 * builds every URL, serialises every body and interprets every status, so these
 * tests exercise the production client rather than a stand-in for it.
 */
export function stubFetch(routes: Record<string, Route | Route[]>): {
  fetchImpl: typeof globalThis.fetch;
  calls: Call[];
} {
  const calls: Call[] = [];
  const cursors = new Map<string, number>();

  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    const key = `${method} ${url}`;
    calls.push({
      method,
      url,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : null,
    });
    const route = routes[key];
    if (route === undefined) {
      throw new TypeError(`no stubbed route for ${key}`);
    }
    const step = Array.isArray(route)
      ? (route[Math.min(cursors.get(key) ?? 0, route.length - 1)] as Route)
      : route;
    cursors.set(key, (cursors.get(key) ?? 0) + 1);
    return new Response(JSON.stringify(step.body), {
      status: step.status,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof globalThis.fetch;

  return { fetchImpl, calls };
}

export function refusal(code: string, message: string): { code: string; message: string } {
  return { code, message };
}
