/**
 * The Kod Zekâsı page, rendered (Command Center Wave 2B, Surface B).
 *
 * NOT A BROWSER TEST. jsdom + React Testing Library, over the real
 * `ArkaliApiClient` with only the network stubbed - the identical tier
 * `providers.test.tsx` already establishes for its own sibling page.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import {
  CODE_INTELLIGENCE_SNAPSHOT,
  CODE_INTELLIGENCE_SNAPSHOT_WITH_VIOLATIONS,
  stubFetch,
  type Route,
} from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const SNAPSHOT = `GET ${BASE}/api/code-intelligence/snapshot`;

function mount(routes: Record<string, Route | Route[]>) {
  const { fetchImpl, calls } = stubFetch(routes);
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const rendered = render(<App client={client} />);
  fireEvent.click(screen.getByRole('button', { name: 'Kod Zekâsı' }));
  return { ...rendered, calls };
}

describe('Code Intelligence page', () => {
  it('is no longer "Yakında" and is reachable from the sidebar', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: CODE_INTELLIGENCE_SNAPSHOT } });

    const navButton = screen.getByRole('button', { name: 'Kod Zekâsı' });
    expect(navButton).not.toHaveTextContent('Yakında');
    expect(navButton).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('heading', { name: 'Kod Zekâsı' })).toBeInTheDocument();
  });

  it('Beginner shows plain-language answers, never internal class names', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: CODE_INTELLIGENCE_SNAPSHOT } });

    expect(await screen.findByText('Yapı sağlıklı görünüyor.')).toBeInTheDocument();
    expect(screen.getByText(/327/)).toBeInTheDocument();
    expect(screen.getByText(/kernel.contracts/)).toBeInTheDocument();
    expect(screen.queryByText('PythonGraphBuilder')).not.toBeInTheDocument();
    expect(screen.queryByText('dependent_count')).not.toBeInTheDocument();
  });

  it('Beginner honestly reports when the architecture gate has real violations', async () => {
    mount({ [SNAPSHOT]: { status: 200, body: CODE_INTELLIGENCE_SNAPSHOT_WITH_VIOLATIONS } });

    expect(await screen.findByText('Yapıda 1 alanda sorun var.')).toBeInTheDocument();
  });

  it('Professional shows the bounded per-area breakdown', async () => {
    const user = userEvent.setup();
    mount({ [SNAPSHOT]: { status: 200, body: CODE_INTELLIGENCE_SNAPSHOT } });
    await screen.findByText('Yapı sağlıklı görünüyor.');

    await user.click(screen.getByRole('button', { name: 'Profesyonel' }));

    expect(await screen.findByText('En çok bağlantılı alanlar')).toBeInTheDocument();
    expect(screen.getByText('113')).toBeInTheDocument();
    // Professional never sees the raw violation detail strings.
    expect(screen.queryByText(/architecture_budget_violation/)).not.toBeInTheDocument();
  });

  it('Expert shows real violation detail strings when present', async () => {
    const user = userEvent.setup();
    mount({ [SNAPSHOT]: { status: 200, body: CODE_INTELLIGENCE_SNAPSHOT_WITH_VIOLATIONS } });
    await screen.findByText('Yapıda 1 alanda sorun var.');

    await user.click(screen.getByRole('button', { name: 'Uzman' }));

    expect(await screen.findByText(/architecture_budget_violation/)).toBeInTheDocument();
  });

  it('presents a failure instead of an empty page when the snapshot cannot be read', async () => {
    mount({ [SNAPSHOT]: { status: 500, body: {} } });

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Kod yapısı okunamadı')).toBeInTheDocument();
  });

  it('retries after a failure and recovers once the backend answers', async () => {
    const user = userEvent.setup();
    mount({
      [SNAPSHOT]: [
        { status: 500, body: {} },
        { status: 200, body: CODE_INTELLIGENCE_SNAPSHOT },
      ],
    });

    const alert = await screen.findByRole('alert');
    await user.click(within(alert).getByRole('button', { name: 'Yeniden dene' }));

    expect(await screen.findByText('Yapı sağlıklı görünüyor.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('issues a fresh GET and recovers the same canonical state on manual refresh', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [SNAPSHOT]: [
        { status: 200, body: CODE_INTELLIGENCE_SNAPSHOT },
        { status: 200, body: CODE_INTELLIGENCE_SNAPSHOT },
      ],
    });

    await screen.findByText('Yapı sağlıklı görünüyor.');
    const before = calls.filter((call) => call.url.endsWith('/api/code-intelligence/snapshot')).length;

    await user.click(screen.getByRole('button', { name: 'Yenile' }));

    await waitFor(() => {
      const after = calls.filter((call) => call.url.endsWith('/api/code-intelligence/snapshot')).length;
      expect(after).toBe(before + 1);
    });
    expect(await screen.findByText('Yapı sağlıklı görünüyor.')).toBeInTheDocument();
  });
});
