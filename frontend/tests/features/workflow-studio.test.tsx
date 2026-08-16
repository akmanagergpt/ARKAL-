/**
 * The Visual Workflow Studio slice, rendered.
 *
 * NOT A BROWSER TEST. This is jsdom with React Testing Library — a component
 * and integration tier. The T10 browser/E2E journey is a separate spec
 * (`frontend/tests/e2e/workflow-studio.spec.ts`); nothing here may be
 * reported as that tier.
 *
 * The whole application is mounted against the real `ArkaliApiClient`; only
 * the network beneath it is controlled, so every assertion exercises the
 * production request-building, status-interpretation and refresh paths for
 * the C-20 routes.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import {
  EMPTY_LIST,
  LIFECYCLE,
  PUBLISHED_REVISION,
  SUCCEEDED_EXECUTION,
  WAITING_APPROVAL_EXECUTION,
  stubFetch,
} from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const PROJECT_LIST = `GET ${BASE}/api/projects`;
const LIFECYCLE_ROUTE = `GET ${BASE}/api/lifecycle/project`;
const LATEST_REVISION = `GET ${BASE}/api/workflows/wf-studio`;
const PUBLISH_REVISION = `POST ${BASE}/api/workflows/wf-studio/revisions`;
const START_EXECUTION = `POST ${BASE}/api/workflows/wf-studio/executions`;
const APPROVE_EXECUTION =
  `POST ${BASE}/api/workflows/wf-studio/executions/exec-studio-1/approve`;

const baseRoutes = {
  [PROJECT_LIST]: { status: 200, body: EMPTY_LIST },
  [LIFECYCLE_ROUTE]: { status: 200, body: LIFECYCLE },
};

async function openStudio(routes: Parameters<typeof stubFetch>[0]) {
  const { fetchImpl, calls } = stubFetch({ ...baseRoutes, ...routes });
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const view = render(<App client={client} />);
  const user = userEvent.setup();
  await user.click(view.getByRole('button', { name: 'Workflow Studio' }));
  return { ...view, calls, user };
}

describe('Visual Workflow Studio page', () => {
  it('shows an honest empty canvas when no revision exists yet', async () => {
    const { user } = await openStudio({
      [LATEST_REVISION]: { status: 404, body: {} },
    });

    await user.click(screen.getByRole('button', { name: /load latest revision/i }));

    expect(
      await screen.findByText('No revision published for this identifier yet.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('No nodes yet. Add one from the palette to begin composing a graph.'),
    ).toBeInTheDocument();
  });

  it('composes a node from the palette and publishes it as a revision', async () => {
    const { user, calls } = await openStudio({
      [PUBLISH_REVISION]: { status: 201, body: PUBLISHED_REVISION },
    });

    await user.click(screen.getByRole('button', { name: '+ trigger' }));
    await user.click(screen.getByRole('button', { name: /publish revision/i }));

    expect(
      await screen.findByText(/Revision 1 \(1\.0\.0\) published for wf-studio\./),
    ).toBeInTheDocument();

    const publishCall = calls.find((call) => call.url === `${BASE}/api/workflows/wf-studio/revisions`);
    const body = publishCall?.body as { nodes: unknown[]; edges: unknown[]; semver_bump: string };
    expect(body.nodes).toHaveLength(1);
    expect(body.edges).toHaveLength(0);
    expect(body.semver_bump).toBe('PATCH');
    expect((body.nodes[0] as { kind: string }).kind).toBe('trigger');
  });

  it('starts an execution, shows a HUMAN APPROVAL pause, and completes it on approval', async () => {
    const { user, calls } = await openStudio({
      [START_EXECUTION]: { status: 201, body: WAITING_APPROVAL_EXECUTION },
      [APPROVE_EXECUTION]: { status: 200, body: SUCCEEDED_EXECUTION },
    });

    await user.click(screen.getByRole('button', { name: /start execution/i }));

    expect(await screen.findByText('WAITING_APPROVAL')).toBeInTheDocument();
    const approveButton = await screen.findByRole('button', { name: /approve n-approval/i });
    await user.click(approveButton);

    expect(await screen.findByText('SUCCEEDED')).toBeInTheDocument();
    const approveCall = calls.find((call) => call.url.endsWith('/approve'));
    expect(approveCall?.body).toEqual({
      node_id: 'n-approval',
      actor: 'human-reviewer',
      decision: 'APPROVED',
      approved_revision_hash: 'sha256:abc123',
    });
  });

  it('reports a refused publish with the backend code and message', async () => {
    const { user } = await openStudio({
      [PUBLISH_REVISION]: {
        status: 400,
        body: { detail: { code: 'EMPTY_GRAPH', message: 'a canonical workflow graph declares no nodes' } },
      },
    });

    await user.click(screen.getByRole('button', { name: '+ trigger' }));
    await user.click(screen.getByRole('button', { name: /publish revision/i }));

    expect(
      await screen.findByText('a canonical workflow graph declares no nodes'),
    ).toBeInTheDocument();
    expect(screen.getByText('EMPTY_GRAPH')).toBeInTheDocument();
  });
});
