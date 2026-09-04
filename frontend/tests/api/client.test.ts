/**
 * The typed API client is the slice's only transport boundary, so it is tested
 * as one: URLs, methods, bodies, and the difference between a refusal (an
 * answer) and unavailability (no answer).
 */

import { describe, expect, it } from 'vitest';

import { ApiRefusal, ApiUnavailable, ArkaliApiClient, ENDPOINTS } from '@/api/client';
import { DRAFT_PROJECT, LIFECYCLE, listOf, stubFetch } from '../fixtures';

const BASE = 'http://127.0.0.1:8000';

function clientWith(routes: Parameters<typeof stubFetch>[0]) {
  const { fetchImpl, calls } = stubFetch(routes);
  return { client: new ArkaliApiClient({ baseUrl: BASE, fetchImpl }), calls };
}

describe('ArkaliApiClient', () => {
  it('reads the project list from the declared route', async () => {
    const { client, calls } = clientWith({
      [`GET ${BASE}/api/projects`]: { status: 200, body: listOf(DRAFT_PROJECT) },
    });

    const page = await client.listProjects();

    expect(page.projects).toHaveLength(1);
    expect(page.projects[0]?.project_id).toBe('prj-alpha');
    expect(calls[0]?.url).toBe(`${BASE}/api/projects`);
  });

  it('posts a create request with the contract body shape', async () => {
    const { client, calls } = clientWith({
      [`POST ${BASE}/api/projects`]: { status: 201, body: DRAFT_PROJECT },
    });

    await client.createProject({ project_id: 'prj-alpha', name: 'Alpha Programme' });

    expect(calls[0]).toMatchObject({
      method: 'POST',
      url: `${BASE}/api/projects`,
      body: { project_id: 'prj-alpha', name: 'Alpha Programme' },
    });
  });

  it('expands path parameters and encodes them', async () => {
    const { client, calls } = clientWith({
      [`GET ${BASE}/api/projects/prj%2Falpha`]: { status: 200, body: DRAFT_PROJECT },
    });

    await client.getProject('prj/alpha');

    expect(calls[0]?.url).toBe(`${BASE}/api/projects/prj%2Falpha`);
  });

  it('requests a transition without judging whether it is legal', async () => {
    const { client, calls } = clientWith({
      [`POST ${BASE}/api/projects/prj-alpha/transitions`]: {
        status: 200,
        body: DRAFT_PROJECT,
      },
    });

    await client.transitionProject('prj-alpha', { target: 'ANYTHING_AT_ALL' });

    expect(calls[0]?.body).toEqual({ target: 'ANYTHING_AT_ALL' });
  });

  it('surfaces a 4xx as a refusal carrying the backend code and message', async () => {
    const { client } = clientWith({
      [`POST ${BASE}/api/projects/prj-alpha/transitions`]: {
        status: 409,
        body: {
          detail: { code: 'FORBIDDEN_TRANSITION', message: 'DRAFT to ACTIVE is forbidden' },
        },
      },
    });

    const error = await client
      .transitionProject('prj-alpha', { target: 'ACTIVE' })
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiRefusal);
    expect((error as ApiRefusal).code).toBe('FORBIDDEN_TRANSITION');
    expect((error as ApiRefusal).message).toBe('DRAFT to ACTIVE is forbidden');
    expect((error as ApiRefusal).status).toBe(409);
  });

  it('does not invent an explanation for an undocumented refusal body', async () => {
    const { client } = clientWith({
      [`GET ${BASE}/api/projects/prj-alpha`]: { status: 404, body: { oops: true } },
    });

    const error = (await client
      .getProject('prj-alpha')
      .catch((caught: unknown) => caught)) as ApiRefusal;

    expect(error).toBeInstanceOf(ApiRefusal);
    expect(error.code).toBe('UNSPECIFIED');
  });

  it('reports a 5xx as unavailability rather than as a refusal', async () => {
    const { client } = clientWith({
      [`GET ${BASE}/api/projects`]: { status: 500, body: {} },
    });

    const error = await client.listProjects().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiUnavailable);
    expect(error).not.toBeInstanceOf(ApiRefusal);
  });

  it('reports a transport failure as unavailability', async () => {
    const client = new ArkaliApiClient({
      baseUrl: BASE,
      fetchImpl: (() => Promise.reject(new Error('connection refused'))) as typeof fetch,
    });

    const error = (await client.health().catch((caught: unknown) => caught)) as ApiUnavailable;

    expect(error).toBeInstanceOf(ApiUnavailable);
    expect(error.message).toContain('connection refused');
  });

  it('reads the lifecycle vocabulary from the API rather than declaring it', async () => {
    const { client } = clientWith({
      [`GET ${BASE}/api/lifecycle/project`]: { status: 200, body: LIFECYCLE },
    });

    const machine = await client.lifecycleStates();

    expect(machine.machine).toBe('Project');
    expect(machine.states).toEqual(LIFECYCLE.states);
  });

  it('reads the operations snapshot from the declared route', async () => {
    const snapshot = {
      runtime: {
        jobs_active: { dimension: 'jobs_active', state: 'PASS', detail: '', value: 0 },
        jobs_queued: { dimension: 'jobs_queued', state: 'PASS', detail: '', value: 0 },
        jobs_stuck: { dimension: 'jobs_stuck', state: 'PASS', detail: '', value: 0 },
        workflows_active: { dimension: 'workflows_active', state: 'PASS', detail: '', value: 0 },
        providers: { dimension: 'providers', state: 'NOT_CONFIGURED', detail: 'no provider', value: null },
        agents: { dimension: 'agents', state: 'NOT_CONFIGURED', detail: 'no agent', value: null },
        workers: { dimension: 'workers', state: 'NOT_CONFIGURED', detail: 'no worker', value: null },
      },
      hardware: {
        cpu_logical_cores: { dimension: 'cpu_logical_cores', state: 'PASS', detail: '', value: 8 },
        ram_total_bytes: { dimension: 'ram_total_bytes', state: 'PASS', detail: '', value: 1 },
        disk_free_bytes: { dimension: 'disk_free_bytes', state: 'PASS', detail: '', value: 1 },
        network_reachable: { dimension: 'network_reachable', state: 'PASS', detail: '', value: 1 },
        gpu_present: { dimension: 'gpu_present', state: 'NOT_APPLICABLE', detail: 'no gpu', value: null },
        vram_total_bytes: { dimension: 'vram_total_bytes', state: 'NOT_APPLICABLE', detail: 'no gpu', value: null },
      },
      storage: {
        database_reachable: { dimension: 'database_reachable', state: 'PASS', detail: '', value: 1 },
        database_size_bytes: { dimension: 'database_size_bytes', state: 'PASS', detail: '', value: 1 },
      },
    };
    const { client, calls } = clientWith({
      [`GET ${BASE}/api/operations/snapshot`]: { status: 200, body: snapshot },
    });

    const result = await client.operationsSnapshot();

    expect(result).toEqual(snapshot);
    expect(calls[0]?.url).toBe(`${BASE}/api/operations/snapshot`);
    expect(calls[0]?.method).toBe('GET');
  });

  it('declares every route as data so the drift control can compare it', () => {
    expect(Object.values(ENDPOINTS).map((route) => `${route.method} ${route.path}`)).toEqual([
      'GET /api/health',
      'GET /api/lifecycle/project',
      'GET /api/projects',
      'POST /api/projects',
      'GET /api/projects/{project_id}',
      'POST /api/projects/{project_id}/transitions',
      'POST /api/projects/{project_id}/revisions',
      'POST /api/workflows/{workflow_id}/revisions',
      'GET /api/workflows/{workflow_id}',
      'GET /api/workflows/{workflow_id}/revisions',
      'GET /api/workflows/{workflow_id}/revisions/{revision_number}',
      'POST /api/workflows/{workflow_id}/executions',
      'GET /api/workflows/{workflow_id}/executions/{execution_id}',
      'POST /api/workflows/{workflow_id}/executions/{execution_id}/signal',
      'POST /api/workflows/{workflow_id}/executions/{execution_id}/approve',
      'GET /api/operations/snapshot',
      'GET /api/factory/history',
      'POST /api/factory/goals',
      'POST /api/candidates/{candidate_id}/preview',
      'GET /api/candidates/{candidate_id}/preview',
      'GET /api/jobs/{job_id}',
      'GET /api/jobs/{job_id}/checkpoints',
      'POST /api/jobs/{job_id}/cancel',
    ]);
  });
});
