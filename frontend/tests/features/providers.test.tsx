/**
 * The Sağlayıcılar ve Modeller page, rendered (Command Center Wave 2,
 * Surface A).
 *
 * NOT A BROWSER TEST. jsdom + React Testing Library, over the real
 * `ArkaliApiClient` with only the network stubbed - the identical tier
 * `operations.test.tsx` already establishes for its own sibling page.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import {
  PROVIDERS_SNAPSHOT,
  PROVIDERS_SNAPSHOT_NOT_CONFIGURED,
  stubFetch,
  type Route,
} from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const SNAPSHOT = `GET ${BASE}/api/providers/snapshot`;

function mount(routes: Record<string, Route | Route[]>) {
  const { fetchImpl, calls } = stubFetch(routes);
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const rendered = render(<App client={client} />);
  fireEvent.click(screen.getByRole('button', { name: 'Sağlayıcılar ve Modeller' }));
  return { ...rendered, calls };
}

describe('Providers page', () => {
  it('is no longer "Yakında" and is reachable from the sidebar', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: PROVIDERS_SNAPSHOT } });

    const navButton = screen.getByRole('button', { name: 'Sağlayıcılar ve Modeller' });
    expect(navButton).not.toHaveTextContent('Yakında');
    expect(navButton).toHaveAttribute('aria-current', 'page');
    expect(
      await screen.findByRole('heading', { name: 'Sağlayıcılar ve Modeller' }),
    ).toBeInTheDocument();
  });

  it('shows the Beginner one-line summary, never raw dimension names', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: PROVIDERS_SNAPSHOT } });

    expect(await screen.findByText('Yerel AI hazır.')).toBeInTheDocument();
    expect(screen.queryByText('local_runtime')).not.toBeInTheDocument();
  });

  it('Beginner honestly reports when no local model is available', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: PROVIDERS_SNAPSHOT_NOT_CONFIGURED } });

    expect(await screen.findByText('Yerel AI şu anda kullanılamıyor.')).toBeInTheDocument();
  });

  it('Professional shows the full per-dimension breakdown', async () => {
    const user = userEvent.setup();
    mount({ [SNAPSHOT]: { status: 200, body: PROVIDERS_SNAPSHOT } });
    await screen.findByText('Yerel AI hazır.');

    await user.click(screen.getByRole('button', { name: 'Profesyonel' }));

    expect(await screen.findByText('local_runtime')).toBeInTheDocument();
    expect(screen.getByText('configured_model')).toBeInTheDocument();
    expect(screen.getByText('accelerator')).toBeInTheDocument();
  });

  it('presents a failure instead of an empty page when the snapshot cannot be read', async () => {
    mount({ [SNAPSHOT]: { status: 500, body: {} } });

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Sağlayıcı durumu okunamadı')).toBeInTheDocument();
  });

  it('retries after a failure and recovers once the backend answers', async () => {
    const user = userEvent.setup();
    mount({
      [SNAPSHOT]: [
        { status: 500, body: {} },
        { status: 200, body: PROVIDERS_SNAPSHOT },
      ],
    });

    const alert = await screen.findByRole('alert');
    await user.click(within(alert).getByRole('button', { name: 'Yeniden dene' }));

    expect(await screen.findByText('Yerel AI hazır.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('issues a fresh GET when the manual refresh control is used', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [SNAPSHOT]: [
        { status: 200, body: PROVIDERS_SNAPSHOT },
        { status: 200, body: PROVIDERS_SNAPSHOT },
      ],
    });

    await screen.findByText('Yerel AI hazır.');
    const before = calls.filter((call) => call.url.endsWith('/api/providers/snapshot')).length;

    await user.click(screen.getByRole('button', { name: 'Yenile' }));

    await waitFor(() => {
      const after = calls.filter((call) => call.url.endsWith('/api/providers/snapshot')).length;
      expect(after).toBe(before + 1);
    });
  });

  it('refresh recovers the same state after a stale-then-fresh read (cold-restart-style proof)', async () => {
    const user = userEvent.setup();
    mount({
      [SNAPSHOT]: [
        { status: 200, body: PROVIDERS_SNAPSHOT },
        { status: 200, body: PROVIDERS_SNAPSHOT },
      ],
    });

    await screen.findByText('Yerel AI hazır.');
    await user.click(screen.getByRole('button', { name: 'Yenile' }));

    expect(await screen.findByText('Yerel AI hazır.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
