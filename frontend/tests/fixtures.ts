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
  FactoryHistorySnapshot,
  LifecycleMachineResponse,
  OperationsSnapshot,
  ProjectDetailResponse,
  ProjectListResponse,
  WorkflowExecutionDetailResponse,
  WorkflowRevisionDetailResponse,
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

export const PUBLISHED_REVISION: WorkflowRevisionDetailResponse = {
  workflow_id: 'wf-studio',
  revision_number: 1,
  semver: '1.0.0',
  revision_hash: 'sha256:abc123',
  created_at: '2026-08-09T09:00:00Z',
  nodes: [
    {
      node_id: 'n-trigger',
      kind: 'trigger',
      control_construct: null,
      label: 'Start',
      parameters: {},
      position_x: 80,
      position_y: 80,
    },
    {
      node_id: 'n-approval',
      kind: 'logic',
      control_construct: 'HUMAN APPROVAL',
      label: 'HUMAN APPROVAL',
      parameters: {},
      position_x: 280,
      position_y: 80,
    },
  ],
  edges: [
    {
      edge_id: 'e-1',
      source_node_id: 'n-trigger',
      target_node_id: 'n-approval',
      condition: null,
    },
  ],
};

export const WAITING_APPROVAL_EXECUTION: WorkflowExecutionDetailResponse = {
  execution_id: 'exec-studio-1',
  workflow_id: 'wf-studio',
  revision_number: 1,
  bound_revision_hash: 'sha256:abc123',
  lifecycle_state: 'WAITING_APPROVAL',
  pending_approval_node_id: 'n-approval',
  created_at: '2026-08-09T09:01:00Z',
  updated_at: '2026-08-09T09:01:00Z',
  evidence: [
    {
      sequence: 1,
      node_id: 'n-trigger',
      kind: 'trigger',
      control_construct: null,
      revision_hash: 'sha256:abc123',
      outcome: 'DISPATCHED',
      job_id: 'exec-studio-1:n-trigger:1',
      recorded_at: '2026-08-09T09:01:00Z',
    },
  ],
};

export const SUCCEEDED_EXECUTION: WorkflowExecutionDetailResponse = {
  ...WAITING_APPROVAL_EXECUTION,
  lifecycle_state: 'SUCCEEDED',
  pending_approval_node_id: null,
};

export const OPERATIONS_SNAPSHOT: OperationsSnapshot = {
  runtime: {
    jobs_active: { dimension: 'jobs_active', state: 'PASS', detail: 'live job count', value: 2 },
    jobs_queued: { dimension: 'jobs_queued', state: 'PASS', detail: 'live queue depth', value: 0 },
    jobs_stuck: { dimension: 'jobs_stuck', state: 'PASS', detail: 'no stuck jobs', value: 0 },
    workflows_active: {
      dimension: 'workflows_active', state: 'PASS', detail: 'live executions', value: 1,
    },
    providers: {
      dimension: 'providers', state: 'NOT_CONFIGURED', detail: 'no provider registered', value: null,
    },
    agents: { dimension: 'agents', state: 'NOT_CONFIGURED', detail: 'no agent registered', value: null },
    workers: { dimension: 'workers', state: 'NOT_CONFIGURED', detail: 'no worker registered', value: null },
  },
  hardware: {
    cpu_logical_cores: {
      dimension: 'cpu_logical_cores', state: 'PASS', detail: 'host probe', value: 8,
    },
    ram_total_bytes: {
      dimension: 'ram_total_bytes', state: 'PASS', detail: 'host probe', value: 17179869184,
    },
    disk_free_bytes: {
      dimension: 'disk_free_bytes', state: 'PASS', detail: 'host probe', value: 500000000000,
    },
    network_reachable: {
      dimension: 'network_reachable', state: 'PASS', detail: 'host probe', value: 1,
    },
    gpu_present: {
      dimension: 'gpu_present', state: 'NOT_APPLICABLE', detail: 'no gpu detected', value: null,
    },
    vram_total_bytes: {
      dimension: 'vram_total_bytes', state: 'NOT_APPLICABLE', detail: 'no gpu detected', value: null,
    },
  },
  storage: {
    database_reachable: {
      dimension: 'database_reachable', state: 'PASS', detail: 'sqlite ping', value: 1,
    },
    database_size_bytes: {
      dimension: 'database_size_bytes', state: 'PASS', detail: 'sqlite file size', value: 245760,
    },
  },
};

const NOT_CONFIGURED_READING = { state: 'NOT_CONFIGURED' as const, value: null };

export const OPERATIONS_SNAPSHOT_NOT_CONFIGURED: OperationsSnapshot = {
  runtime: {
    jobs_active: { dimension: 'jobs_active', detail: 'no runtime configured', ...NOT_CONFIGURED_READING },
    jobs_queued: { dimension: 'jobs_queued', detail: 'no runtime configured', ...NOT_CONFIGURED_READING },
    jobs_stuck: { dimension: 'jobs_stuck', detail: 'no runtime configured', ...NOT_CONFIGURED_READING },
    workflows_active: {
      dimension: 'workflows_active', detail: 'no runtime configured', ...NOT_CONFIGURED_READING,
    },
    providers: { dimension: 'providers', detail: 'no runtime configured', ...NOT_CONFIGURED_READING },
    agents: { dimension: 'agents', detail: 'no runtime configured', ...NOT_CONFIGURED_READING },
    workers: { dimension: 'workers', detail: 'no runtime configured', ...NOT_CONFIGURED_READING },
  },
  hardware: {
    cpu_logical_cores: {
      dimension: 'cpu_logical_cores', detail: 'no host probe', ...NOT_CONFIGURED_READING,
    },
    ram_total_bytes: { dimension: 'ram_total_bytes', detail: 'no host probe', ...NOT_CONFIGURED_READING },
    disk_free_bytes: { dimension: 'disk_free_bytes', detail: 'no host probe', ...NOT_CONFIGURED_READING },
    network_reachable: {
      dimension: 'network_reachable', detail: 'no host probe', ...NOT_CONFIGURED_READING,
    },
    gpu_present: { dimension: 'gpu_present', detail: 'no gpu detected', ...NOT_CONFIGURED_READING },
    vram_total_bytes: {
      dimension: 'vram_total_bytes', detail: 'no gpu detected', ...NOT_CONFIGURED_READING,
    },
  },
  storage: {
    database_reachable: {
      dimension: 'database_reachable', detail: 'no storage configured', ...NOT_CONFIGURED_READING,
    },
    database_size_bytes: {
      dimension: 'database_size_bytes', detail: 'no storage configured', ...NOT_CONFIGURED_READING,
    },
  },
};

export const FACTORY_HISTORY_SNAPSHOT: FactoryHistorySnapshot = {
  candidates: [
    { candidate_id: 'golden-work-127', state: 'ACCEPTANCE_INTERRUPTED', recorded_at: '2026-08-30T22:00:00Z' },
    { candidate_id: 'golden-work-126', state: 'STAGE_FAILED', recorded_at: '2026-08-30T18:30:00Z' },
  ],
  campaigns: [
    {
      campaign_id: 'student-fee-golden-work-127-20260831',
      max_new_candidates: 1,
      max_total_seconds: 14400,
      max_same_fingerprint_repeats: 2,
      consumed_candidates: 1,
      consumed_seconds: 2418.1,
      status: 'CAMPAIGN_BUDGET_EXHAUSTED',
      attempts: [
        {
          candidate_id: 'golden-work-127',
          outcome: 'STAGED_GENERATION_PASS',
          failure_class: null,
          fingerprint: null,
          elapsed_seconds: 2418.1,
          recorded_at: '2026-08-30T21:50:00Z',
        },
      ],
    },
  ],
};

export const FACTORY_HISTORY_EMPTY: FactoryHistorySnapshot = { candidates: [], campaigns: [] };
