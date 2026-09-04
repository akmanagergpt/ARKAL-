/**
 * The real "Yeni Uygulama" goal-intake form, rendered.
 *
 * NOT A BROWSER TEST. jsdom + React Testing Library, over the real
 * `ArkaliApiClient` with only the network stubbed - see
 * `project-registry.test.tsx`'s own note for why that is the right tier here.
 *
 * Every case here mounts the real `App` and drives the real
 * `POST /api/factory/goals` request-building and response-interpretation
 * path - the same path a live submission takes.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import type { _FactoryIntakeResponse } from '@/api/contracts';
import { stubFetch, type Route } from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const GOALS = `POST ${BASE}/api/factory/goals`;
const HISTORY = `GET ${BASE}/api/factory/history`;
const FACTORY_HISTORY_EMPTY = { candidates: [], campaigns: [] };

function mount(routes: Record<string, Route | Route[]>) {
  const { fetchImpl, calls } = stubFetch({
    [HISTORY]: { status: 200, body: FACTORY_HISTORY_EMPTY },
    ...routes,
  });
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const rendered = render(<App client={client} />);
  fireEvent.click(screen.getByRole('button', { name: 'AI Software Factory' }));
  return { ...rendered, calls };
}

const GOVERNED_STOP: _FactoryIntakeResponse = {
  request_id: 'goal-1',
  goal_id: 'sha256:goal',
  blueprint_id: 'sha256:blueprint',
  state: 'governed_stop',
  selected_tier: null,
  unresolved_count: 1,
  unresolved: [
    { subject_index: 0, kind: 'missing_acceptance_criteria', detail: 'statement 0 yields no mechanically derivable acceptance criterion' },
  ],
  durable_job_id: null,
};

const ESCALATED: _FactoryIntakeResponse = {
  request_id: 'goal-2',
  goal_id: 'sha256:goal2',
  blueprint_id: 'sha256:blueprint2',
  state: 'escalated',
  selected_tier: 'human_governance',
  unresolved_count: 0,
  unresolved: [],
  durable_job_id: null,
};

const QUEUED: _FactoryIntakeResponse = {
  request_id: 'goal-3',
  goal_id: 'sha256:goal3',
  blueprint_id: 'sha256:blueprint3',
  state: 'queued',
  selected_tier: 'local_model',
  unresolved_count: 0,
  unresolved: [],
  durable_job_id: 'goal-3',
};

async function typeAndSubmit(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByLabelText(/nasıl bir uygulama yapmak istiyorsunuz/i), text);
  await user.click(screen.getByRole('button', { name: 'Uygulamayı Oluştur' }));
}

describe('New Application intake', () => {
  it('keeps submit disabled until real text is entered', async () => {
    mount({});
    expect(screen.getByRole('button', { name: 'Uygulamayı Oluştur' })).toBeDisabled();
  });

  it('explains a governed_stop honestly, in Turkish, without technical jargon in beginner mode', async () => {
    const user = userEvent.setup();
    mount({ [GOALS]: { status: 202, body: GOVERNED_STOP } });

    await typeAndSubmit(user, 'Stok takibi yapabileceğim bir uygulama istiyorum.');

    expect(await screen.findByText('İsteğiniz otomatik olarak işlenemedi')).toBeInTheDocument();
    expect(screen.getByText(/otomatik olarak doğrulanabilir bir kural çıkaramadı/)).toBeInTheDocument();
    expect(screen.queryByText('missing_acceptance_criteria')).not.toBeInTheDocument();
    expect(screen.queryByText(/goal_id/)).not.toBeInTheDocument();
  });

  it('shows the real kind and detail in Uzman mode', async () => {
    const user = userEvent.setup();
    mount({ [GOALS]: { status: 202, body: GOVERNED_STOP } });
    await user.click(screen.getByRole('button', { name: 'Uzman' }));

    await typeAndSubmit(user, 'Stok takibi yapabileceğim bir uygulama istiyorum.');

    expect(await screen.findByText(/missing_acceptance_criteria/)).toBeInTheDocument();
    expect(screen.getByText(/statement 0 yields no mechanically derivable/)).toBeInTheDocument();
    expect(screen.getByText(/goal_id: sha256:goal/)).toBeInTheDocument();
  });

  it('explains an escalated result honestly, without claiming production started', async () => {
    const user = userEvent.setup();
    mount({ [GOALS]: { status: 202, body: ESCALATED } });

    await typeAndSubmit(
      user,
      'The system must respond within at least 500 ms. The system must support at least 10 users.',
    );

    expect(await screen.findByText('İsteğiniz insan onayı gerektiriyor')).toBeInTheDocument();
    expect(screen.getByText(/kendiliğinden üretime alacak bir yapılandırmaya sahip değil/)).toBeInTheDocument();
  });

  it('explains a queued result and polls the real job honestly, without fabricating progress', async () => {
    const user = userEvent.setup();
    const JOB = `GET ${BASE}/api/jobs/goal-3`;
    const CHECKPOINTS = `GET ${BASE}/api/jobs/goal-3/checkpoints`;
    mount({
      [GOALS]: { status: 202, body: QUEUED },
      [JOB]: {
        status: 200,
        body: {
          job_id: 'goal-3', job_type: 'software_factory.production',
          idempotency_key: 'goal-3', lifecycle_state: 'QUEUED',
          created_at: '2026-09-04T00:00:00Z',
        },
      },
      [CHECKPOINTS]: { status: 200, body: [] },
    });

    await typeAndSubmit(
      user,
      'The system must respond within at least 500 ms. The system must support at least 10 users.',
    );

    expect(await screen.findByText('İsteğiniz sıraya alındı')).toBeInTheDocument();
    // The real job's real state, read from the real job store — not a
    // fabricated staged animation.
    expect(await screen.findByText('İstek alındı, sırada bekliyor')).toBeInTheDocument();
    expect(
      screen.getByText(/onu işleyecek bir arka plan süreci \(worker\) çalışmıyorsa/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Hazır$/)).not.toBeInTheDocument();
  });

  it('shows a real SUCCEEDED job and its real checkpoints as done, in Uzman mode', async () => {
    const user = userEvent.setup();
    const JOB = `GET ${BASE}/api/jobs/goal-3`;
    const CHECKPOINTS = `GET ${BASE}/api/jobs/goal-3/checkpoints`;
    mount({
      [GOALS]: { status: 202, body: QUEUED },
      [JOB]: {
        status: 200,
        body: {
          job_id: 'goal-3', job_type: 'software_factory.production',
          idempotency_key: 'goal-3', lifecycle_state: 'SUCCEEDED',
          created_at: '2026-09-04T00:00:00Z',
        },
      },
      [CHECKPOINTS]: {
        status: 200,
        body: [
          {
            sequence: 1,
            payload: { phase: 'staged_generation_pass', candidate_id: 'factory-goal-3' },
            recorded_at: '2026-09-04T00:05:00Z',
          },
        ],
      },
    });
    await user.click(screen.getByRole('button', { name: 'Uzman' }));

    await typeAndSubmit(
      user,
      'The system must respond within at least 500 ms. The system must support at least 10 users.',
    );

    expect(await screen.findByText('İlk üretim aşaması tamamlandı')).toBeInTheDocument();
    expect(screen.getByText(/lifecycle_state: SUCCEEDED/)).toBeInTheDocument();
    expect(screen.getByText(/factory-goal-3/)).toBeInTheDocument();
  });

  it('reports a transport failure rather than a fabricated result', async () => {
    const user = userEvent.setup();
    mount({ [GOALS]: { status: 503, body: null } });

    await typeAndSubmit(user, 'Stok takibi yapabileceğim bir uygulama istiyorum.');

    expect(await screen.findByText('İstek gönderilemedi')).toBeInTheDocument();
  });

  it('sends the real, unmodified goal text and a real request id', async () => {
    const user = userEvent.setup();
    const { calls } = mount({ [GOALS]: { status: 202, body: GOVERNED_STOP } });

    await typeAndSubmit(user, 'Stok takibi yapabileceğim bir uygulama istiyorum.');
    await screen.findByText('İsteğiniz otomatik olarak işlenemedi');

    const call = calls.find((c) => c.method === 'POST' && c.url.endsWith('/api/factory/goals'));
    const body = call?.body as { goal_text: string; request_id: string; capability_id: string | null };
    expect(body.goal_text).toBe('Stok takibi yapabileceğim bir uygulama istiyorum.');
    expect(body.request_id.length).toBeGreaterThan(0);
    expect(body.capability_id).toBeNull();
  });
});
