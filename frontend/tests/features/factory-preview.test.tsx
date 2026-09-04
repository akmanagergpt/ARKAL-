/**
 * "Uygulamayı Aç" / "Durdur" on the AI Software Factory candidate list.
 *
 * NOT A BROWSER TEST. jsdom + React Testing Library, over the real
 * `ArkaliApiClient` with only the network stubbed — see
 * `project-registry.test.tsx`'s own note for why that is the right tier
 * here. Every case drives the real `GET/POST /api/candidates/{id}/preview`,
 * `GET /api/jobs/{id}`, `GET /api/jobs/{id}/checkpoints` and
 * `POST /api/jobs/{id}/cancel` request-building and response-interpretation
 * path — the same path a live preview takes.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import { stubFetch, type Route } from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const HISTORY = `GET ${BASE}/api/factory/history`;
const FIND_PREVIEW = `GET ${BASE}/api/candidates/golden-work-129/preview`;
const FIND_PREVIEW_130 = `GET ${BASE}/api/candidates/golden-work-130/preview`;
const START = `POST ${BASE}/api/candidates/golden-work-129/preview`;
const JOB = `GET ${BASE}/api/jobs/preview-golden-work-129`;
const CHECKPOINTS = `GET ${BASE}/api/jobs/preview-golden-work-129/checkpoints`;
const CANCEL = `POST ${BASE}/api/jobs/preview-golden-work-129/cancel`;

const ACCEPTED_SNAPSHOT = {
  candidates: [
    { candidate_id: 'golden-work-129', state: 'ACCEPTED', recorded_at: '2026-08-31T16:08:39Z' },
  ],
  campaigns: [],
};
const STAGE_FAILED_SNAPSHOT = {
  candidates: [
    { candidate_id: 'golden-work-130', state: 'STAGE_FAILED', recorded_at: '2026-09-03T09:25:02Z' },
  ],
  campaigns: [],
};

const QUEUED_REF = {
  job_id: 'preview-golden-work-129', job_type: 'candidate.preview',
  idempotency_key: 'golden-work-129', lifecycle_state: 'QUEUED',
  created_at: '2026-09-04T00:00:00Z',
};
const RUNNING_REF = { ...QUEUED_REF, lifecycle_state: 'RUNNING' };
const CANCELLED_REF = { ...QUEUED_REF, lifecycle_state: 'CANCELLED' };

function mount(routes: Record<string, Route | Route[]>) {
  const { fetchImpl, calls } = stubFetch({
    [FIND_PREVIEW]: { status: 200, body: null },
    [FIND_PREVIEW_130]: { status: 200, body: null },
    ...routes,
  });
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const rendered = render(<App client={client} />);
  fireEvent.click(screen.getByRole('button', { name: 'AI Software Factory' }));
  return { ...rendered, calls };
}

describe('Uygulamayı Aç / Durdur', () => {
  it('disables Uygulamayı Aç with a plain-language reason for a non-ACCEPTED candidate', async () => {
    mount({ [HISTORY]: { status: 200, body: STAGE_FAILED_SNAPSHOT } });

    const button = await screen.findByRole('button', { name: 'Uygulamayı Aç' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', expect.stringContaining('STAGE_FAILED'));
  });

  it('enables Uygulamayı Aç for an ACCEPTED candidate and enqueues a real candidate.preview job', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [HISTORY]: { status: 200, body: ACCEPTED_SNAPSHOT },
      [START]: { status: 202, body: QUEUED_REF },
      [CHECKPOINTS]: { status: 200, body: [] },
    });

    const button = await screen.findByRole('button', { name: 'Uygulamayı Aç' });
    expect(button).toBeEnabled();
    await user.click(button);

    await screen.findByText('Sırada bekliyor');
    const call = calls.find((c) => c.method === 'POST' && c.url.endsWith('/preview'));
    expect(call?.url).toBe(`${BASE}/api/candidates/golden-work-129/preview`);
  });

  it('rediscovers a real preview job on mount without creating one', async () => {
    const { calls } = mount({
      [HISTORY]: { status: 200, body: ACCEPTED_SNAPSHOT },
      [FIND_PREVIEW]: { status: 200, body: RUNNING_REF },
      [CHECKPOINTS]: {
        status: 200,
        body: [{ sequence: 1, payload: { phase: 'backend_started' }, recorded_at: 't' }],
      },
    });

    expect(await screen.findByText('Arka uç başlatıldı')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/preview'))).toBe(false);
  });

  it('shows real progress phases from real checkpoints while preparing', async () => {
    const user = userEvent.setup();
    mount({
      [HISTORY]: { status: 200, body: ACCEPTED_SNAPSHOT },
      [START]: { status: 202, body: RUNNING_REF },
      [CHECKPOINTS]: {
        status: 200,
        body: [
          { sequence: 1, payload: { phase: 'workspace_allocated' }, recorded_at: '2026-09-04T00:00:01Z' },
          { sequence: 2, payload: { phase: 'backend_started' }, recorded_at: '2026-09-04T00:00:20Z' },
        ],
      },
    });

    await user.click(await screen.findByRole('button', { name: 'Uygulamayı Aç' }));

    expect(await screen.findByText('Arka uç başlatıldı')).toBeInTheDocument();
  });

  it('shows the real running app link once ready, hides internal detail in Başlangıç mode', async () => {
    const user = userEvent.setup();
    mount({
      [HISTORY]: { status: 200, body: ACCEPTED_SNAPSHOT },
      [START]: { status: 202, body: RUNNING_REF },
      [CHECKPOINTS]: {
        status: 200,
        body: [
          {
            sequence: 1,
            payload: {
              phase: 'ready', candidate_id: 'golden-work-129',
              backend_url: 'http://127.0.0.1:5000', frontend_url: 'http://127.0.0.1:3000',
            },
            recorded_at: '2026-09-04T00:01:00Z',
          },
        ],
      },
    });

    await user.click(await screen.findByRole('button', { name: 'Uygulamayı Aç' }));

    const link = await screen.findByRole('link', { name: /Çalışan uygulamayı aç/ });
    expect(link).toHaveAttribute('href', 'http://127.0.0.1:3000');
    expect(link).toHaveAttribute('target', '_blank');
    expect(screen.queryByText(/job_id:/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Durdur' })).toBeInTheDocument();
  });

  it(
    'calls the real cancel route when Durdur is pressed, honestly shows the request-sent gap, ' +
    'then reflects the worker\'s own real CANCELLED transition once polling observes it',
    async () => {
      const user = userEvent.setup();
      const { calls } = mount({
        [HISTORY]: { status: 200, body: ACCEPTED_SNAPSHOT },
        [START]: { status: 202, body: RUNNING_REF },
        [CHECKPOINTS]: [
          {
            status: 200,
            body: [
              { sequence: 1, payload: { phase: 'ready', frontend_url: 'http://127.0.0.1:3000' }, recorded_at: 't1' },
            ],
          },
          {
            status: 200,
            body: [
              { sequence: 1, payload: { phase: 'ready', frontend_url: 'http://127.0.0.1:3000' }, recorded_at: 't1' },
              { sequence: 2, payload: { phase: 'stopped', reason: 'cancelled' }, recorded_at: 't2' },
            ],
          },
        ],
        [CANCEL]: { status: 200, body: RUNNING_REF }, // real route: no transition, state unchanged
        [JOB]: { status: 200, body: CANCELLED_REF }, // the worker's own later, real transition
      });

      await user.click(await screen.findByRole('button', { name: 'Uygulamayı Aç' }));
      await screen.findByRole('link', { name: /Çalışan uygulamayı aç/ });
      await user.click(screen.getByRole('button', { name: 'Durdur' }));

      const cancelCall = calls.find((c) => c.method === 'POST' && c.url.endsWith('/cancel'));
      expect(cancelCall).toBeDefined();
      await screen.findByText('Durdurma isteği gönderildi…');

      // Real polling (POLL_INTERVAL_MS) is what surfaces the worker's own
      // later, real CANCELLED transition -- never something the click itself
      // fabricates.
      await waitFor(
        () => expect(screen.getByText('Bu önizleme durduruldu.')).toBeInTheDocument(),
        { timeout: 6000 },
      );
    },
    10000,
  );
});
