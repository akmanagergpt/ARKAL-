/**
 * The AI Software Factory history page, rendered.
 *
 * NOT A BROWSER TEST. jsdom + React Testing Library, over the real
 * `ArkaliApiClient` with only the network stubbed - see
 * `project-registry.test.tsx`'s own note for why that is the right tier here.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import { FACTORY_HISTORY_EMPTY, FACTORY_HISTORY_SNAPSHOT, stubFetch, type Route } from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const HISTORY = `GET ${BASE}/api/factory/history`;

function mount(routes: Record<string, Route | Route[]>) {
  const { fetchImpl, calls } = stubFetch(routes);
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const rendered = render(<App client={client} />);
  fireEvent.click(screen.getByRole('button', { name: 'AI Software Factory' }));
  return { ...rendered, calls };
}

describe('AI Software Factory history page', () => {
  it('shows a loading state before the history answers', async () => {
    mount({ [HISTORY]: { status: 200, body: FACTORY_HISTORY_SNAPSHOT } });

    expect(screen.getByText('Üretim geçmişi yükleniyor…')).toBeInTheDocument();
    await screen.findByText('Adaylar (Candidates)');
  });

  it('renders real candidate and campaign records without inventing anything', async () => {
    mount({ [HISTORY]: { status: 200, body: FACTORY_HISTORY_SNAPSHOT } });

    // "golden-work-127" appears twice, honestly: once as a candidate row,
    // once inside its own campaign's attempt history.
    expect(await screen.findAllByText('golden-work-127')).toHaveLength(2);
    expect(screen.getByText('ACCEPTANCE_INTERRUPTED')).toBeInTheDocument();
    expect(screen.getByText('golden-work-126')).toBeInTheDocument();
    expect(screen.getByText('student-fee-golden-work-127-20260831')).toBeInTheDocument();
    expect(screen.getByText('CAMPAIGN_BUDGET_EXHAUSTED')).toBeInTheDocument();
    expect(screen.getByText('1 / 1')).toBeInTheDocument();
  });

  it('never renders a trigger for starting a new golden-work run', async () => {
    mount({ [HISTORY]: { status: 200, body: FACTORY_HISTORY_SNAPSHOT } });
    await screen.findAllByText('golden-work-127');

    expect(
      screen.queryByRole('button', { name: /golden-work|başlat.*(çalışma|run)/i }),
    ).not.toBeInTheDocument();
  });

  it('renders the real goal-intake form above the read-only history', async () => {
    mount({ [HISTORY]: { status: 200, body: FACTORY_HISTORY_SNAPSHOT } });
    await screen.findAllByText('golden-work-127');

    expect(screen.getByLabelText(/nasıl bir uygulama yapmak istiyorsunuz/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Uygulamayı Oluştur' })).toBeInTheDocument();
  });

  it('shows an honest empty state with no candidates or campaigns', async () => {
    mount({ [HISTORY]: { status: 200, body: FACTORY_HISTORY_EMPTY } });

    expect(await screen.findByText('Henüz kayıtlı bir aday yok.')).toBeInTheDocument();
    expect(screen.getByText('Henüz kayıtlı bir kampanya yok.')).toBeInTheDocument();
  });

  it('reports a transport failure rather than showing stale or invented data', async () => {
    mount({ [HISTORY]: { status: 503, body: null } });

    expect(await screen.findByText('Üretim geçmişi okunamadı')).toBeInTheDocument();
  });
});
