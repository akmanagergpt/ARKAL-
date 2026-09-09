/**
 * The Tanılama page, rendered (Command Center Wave 2C, Surface C).
 *
 * NOT A BROWSER TEST. jsdom + React Testing Library, over the real
 * `ArkaliApiClient` with only the network stubbed - the identical tier
 * `providers.test.tsx`/`code-intelligence.test.tsx` already establish for
 * their own sibling pages.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import {
  DIAGNOSTICS_SNAPSHOT_ATTENTION,
  DIAGNOSTICS_SNAPSHOT_HEALTHY,
  stubFetch,
  type Route,
} from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const SNAPSHOT = `GET ${BASE}/api/diagnostics/snapshot`;

function mount(routes: Record<string, Route | Route[]>) {
  const { fetchImpl, calls } = stubFetch(routes);
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const rendered = render(<App client={client} />);
  fireEvent.click(screen.getByRole('button', { name: 'Tanılama' }));
  return { ...rendered, calls };
}

describe('Diagnostics page', () => {
  it('is no longer "Yakında" and is reachable from the sidebar', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: DIAGNOSTICS_SNAPSHOT_HEALTHY } });

    const navButton = screen.getByRole('button', { name: 'Tanılama' });
    expect(navButton).not.toHaveTextContent('Yakında');
    expect(navButton).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('heading', { name: 'Tanılama' })).toBeInTheDocument();
  });

  it('Beginner shows a truthful healthy state, never internal jargon', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: DIAGNOSTICS_SNAPSHOT_HEALTHY } });

    expect(await screen.findByText('Sistem sağlıklı')).toBeInTheDocument();
    expect(screen.getByText('Şu anda yapmanız gereken bir işlem yok.')).toBeInTheDocument();
    expect(screen.queryByText('resolve_open_finding')).not.toBeInTheDocument();
    expect(screen.queryByText('operational_hint')).not.toBeInTheDocument();
  });

  it('Beginner honestly reports when attention is needed, with a real next step', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: DIAGNOSTICS_SNAPSHOT_ATTENTION } });

    expect(await screen.findByText('Dikkat edilmesi gereken sorunlar var')).toBeInTheDocument();
    expect(screen.getByText('Önce açık kritik sorunları çözün.')).toBeInTheDocument();
  });

  it('Professional shows real finding IDs and severities, bounded', async () => {
    const user = userEvent.setup();
    mount({ [SNAPSHOT]: { status: 200, body: DIAGNOSTICS_SNAPSHOT_ATTENTION } });
    await screen.findByText('Dikkat edilmesi gereken sorunlar var');

    await user.click(screen.getByRole('button', { name: 'Profesyonel' }));

    expect(await screen.findByText('F-0099')).toBeInTheDocument();
    expect(screen.getByText('F-0098')).toBeInTheDocument();
    expect(screen.getAllByText('HIGH').length).toBe(2);
    // Professional never sees the raw violation detail strings.
    expect(screen.queryByText(/architecture_budget_violation/)).not.toBeInTheDocument();
  });

  it('Professional shows an honest empty state when no findings are open', async () => {
    const user = userEvent.setup();
    mount({ [SNAPSHOT]: { status: 200, body: DIAGNOSTICS_SNAPSHOT_HEALTHY } });
    await screen.findByText('Sistem sağlıklı');

    await user.click(screen.getByRole('button', { name: 'Profesyonel' }));

    expect(await screen.findByText('Açık bulgu yok.')).toBeInTheDocument();
  });

  it('Expert shows real violation detail strings when present', async () => {
    const user = userEvent.setup();
    mount({ [SNAPSHOT]: { status: 200, body: DIAGNOSTICS_SNAPSHOT_ATTENTION } });
    await screen.findByText('Dikkat edilmesi gereken sorunlar var');

    await user.click(screen.getByRole('button', { name: 'Uzman' }));

    expect(await screen.findByText(/architecture_budget_violation/)).toBeInTheDocument();
  });

  it('presents a failure instead of an empty page when the snapshot cannot be read', async () => {
    mount({ [SNAPSHOT]: { status: 500, body: {} } });

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Sistem durumu okunamadı')).toBeInTheDocument();
  });

  it('retries after a failure and recovers once the backend answers', async () => {
    const user = userEvent.setup();
    mount({
      [SNAPSHOT]: [
        { status: 500, body: {} },
        { status: 200, body: DIAGNOSTICS_SNAPSHOT_HEALTHY },
      ],
    });

    const alert = await screen.findByRole('alert');
    await user.click(within(alert).getByRole('button', { name: 'Yeniden dene' }));

    expect(await screen.findByText('Sistem sağlıklı')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('issues a fresh GET and recovers the same canonical state on manual refresh', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [SNAPSHOT]: [
        { status: 200, body: DIAGNOSTICS_SNAPSHOT_HEALTHY },
        { status: 200, body: DIAGNOSTICS_SNAPSHOT_HEALTHY },
      ],
    });

    await screen.findByText('Sistem sağlıklı');
    const before = calls.filter((call) => call.url.endsWith('/api/diagnostics/snapshot')).length;

    await user.click(screen.getByRole('button', { name: 'Yenile' }));

    await waitFor(() => {
      const after = calls.filter((call) => call.url.endsWith('/api/diagnostics/snapshot')).length;
      expect(after).toBe(before + 1);
    });
    expect(await screen.findByText('Sistem sağlıklı')).toBeInTheDocument();
  });
});
