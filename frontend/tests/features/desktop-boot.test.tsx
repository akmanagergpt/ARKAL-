import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ArkaliApiClient } from '@/api/client';
import { DesktopBootBoundary } from '@/app/DesktopBootBoundary';
import { stubFetch } from '../fixtures';

const BASE = 'http://127.0.0.1:8000';

describe('Desktop startup experience', () => {
  it('renders the Command Center only after the real health contract is ready', async () => {
    const { fetchImpl } = stubFetch({
      [`GET ${BASE}/api/health`]: {
        status: 200,
        body: { status: 'ready', schema_revision: '0011' },
      },
    });
    render(<DesktopBootBoundary client={new ArkaliApiClient({ baseUrl: BASE, fetchImpl })}><p>Command Center hazır</p></DesktopBootBoundary>);
    expect(screen.getByRole('progressbar', { name: 'ARKALI başlatılıyor' })).toBeInTheDocument();
    expect(await screen.findByText('Command Center hazır')).toBeInTheDocument();
  });

  it('shows an actionable error and retries the same health boundary', async () => {
    const user = userEvent.setup();
    const { fetchImpl, calls } = stubFetch({
      [`GET ${BASE}/api/health`]: [
        { status: 503, body: {} },
        { status: 200, body: { status: 'ready', schema_revision: '0011' } },
      ],
    });
    render(<DesktopBootBoundary client={new ArkaliApiClient({ baseUrl: BASE, fetchImpl })}><p>Command Center hazır</p></DesktopBootBoundary>);
    expect(await screen.findByText('Command Center başlatılamadı')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Yeniden dene' }));
    expect(await screen.findByText('Command Center hazır')).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });
});
