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

  it('declares every route as data so the drift control can compare it', () => {
    expect(Object.values(ENDPOINTS).map((route) => `${route.method} ${route.path}`)).toEqual([
      'GET /api/health',
      'GET /api/lifecycle/project',
      'GET /api/projects',
      'POST /api/projects',
      'GET /api/projects/{project_id}',
      'POST /api/projects/{project_id}/transitions',
      'POST /api/projects/{project_id}/revisions',
    ]);
  });
});
