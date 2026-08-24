/**
 * The Operations page, rendered (`ARK-REQ-0396`, D-028).
 *
 * NOT A BROWSER TEST. jsdom + React Testing Library, over the real
 * `ArkaliApiClient` with only the network stubbed - see
 * `project-registry.test.tsx`'s own note for why that is the right tier here.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import {
  OPERATIONS_SNAPSHOT,
  OPERATIONS_SNAPSHOT_NOT_CONFIGURED,
  stubFetch,
  type Route,
} from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const SNAPSHOT = `GET ${BASE}/api/operations/snapshot`;

function mount(routes: Record<string, Route | Route[]>) {
  const { fetchImpl, calls } = stubFetch(routes);
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const rendered = render(<App client={client} />);
  fireEvent.click(screen.getByRole('button', { name: 'Operasyonlar' }));
  return { ...rendered, calls };
}

describe('Operations page', () => {
  it('shows a loading state before the snapshot answers', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: OPERATIONS_SNAPSHOT } });

    expect(screen.getByText('Operasyon verileri yükleniyor…')).toBeInTheDocument();
    await screen.findByText('Çalışma zamanı');
  });

  it('renders a real snapshot without inventing values for unconfigured dimensions', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: OPERATIONS_SNAPSHOT } });

    expect(await screen.findByText('Çalışma zamanı')).toBeInTheDocument();
    // A real, present dimension shows the backend's own value.
    expect(screen.getByText('2')).toBeInTheDocument();
    // A NOT_CONFIGURED dimension shows its state, never a fabricated number.
    const providersRow = screen.getByText('providers').closest('div')!.parentElement!;
    expect(within(providersRow).getByText('NOT_CONFIGURED')).toBeInTheDocument();
    expect(within(providersRow).queryByText(/^\d/)).not.toBeInTheDocument();
  });

  it('shows an honest "not configured" summary when nothing is active', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: OPERATIONS_SNAPSHOT_NOT_CONFIGURED } });

    expect(await screen.findByText('Henüz yapılandırılmamış')).toBeInTheDocument();
    // The per-dimension grid is still rendered honestly underneath.
    expect(screen.getAllByText('NOT_CONFIGURED').length).toBeGreaterThan(0);
  });

  it('presents a failure instead of an empty page when the snapshot cannot be read', async () => {
    mount({ [SNAPSHOT]: { status: 500, body: {} } });

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Operasyon verileri okunamadı')).toBeInTheDocument();
    expect(screen.queryByText('Çalışma zamanı')).not.toBeInTheDocument();
  });

  it('never renders a raw stack trace on failure', async () => {
    mount({ [SNAPSHOT]: { status: 500, body: {} } });

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).not.toMatch(/at .*\(.*:\d+:\d+\)/);
    expect(alert.textContent).not.toContain('TypeError');
  });

  it('retries after a failure and recovers once the backend answers', async () => {
    const user = userEvent.setup();
    mount({
      [SNAPSHOT]: [
        { status: 500, body: {} },
        { status: 200, body: OPERATIONS_SNAPSHOT },
      ],
    });

    const alert = await screen.findByRole('alert');
    await user.click(within(alert).getByRole('button', { name: 'Yeniden dene' }));

    expect(await screen.findByText('Çalışma zamanı')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('issues a fresh GET when the manual refresh control is used', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [SNAPSHOT]: [
        { status: 200, body: OPERATIONS_SNAPSHOT },
        { status: 200, body: OPERATIONS_SNAPSHOT },
      ],
    });

    await screen.findByText('Çalışma zamanı');
    const before = calls.filter((call) => call.url.endsWith('/api/operations/snapshot')).length;

    await user.click(screen.getByRole('button', { name: 'Yenile' }));

    await waitFor(() => {
      const after = calls.filter((call) => call.url.endsWith('/api/operations/snapshot')).length;
      expect(after).toBe(before + 1);
    });
  });

  it('is reachable from the sidebar with an accessible current-page indicator', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: OPERATIONS_SNAPSHOT } });

    const navButton = screen.getByRole('button', { name: 'Operasyonlar' });
    expect(navButton).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('heading', { name: 'Operasyonlar' })).toBeInTheDocument();
  });
});
