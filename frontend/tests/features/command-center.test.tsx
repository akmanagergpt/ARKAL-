import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ArkaliApiClient } from '@/api/client';
import { App } from '@/app/App';
import { stubFetch } from '../fixtures';

function mount() {
  const { fetchImpl } = stubFetch({});
  render(<App client={new ArkaliApiClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })} />);
}

describe('Command Center skill modes', () => {
  it('starts in the guided Beginner presentation', () => {
    mount();
    expect(screen.getByRole('button', { name: 'Başlangıç' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Bugün ne üzerinde çalışmak istiyorsunuz?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Workflow Studio Uzman/ })).toBeDisabled();
    expect(screen.queryByText('Gelişmiş stüdyoyu aç')).not.toBeInTheDocument();
  });

  it('exposes Workflow Studio only in Expert and exits it when complexity is lowered', async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole('button', { name: 'Uzman' }));
    const workflow = screen.getByRole('button', { name: 'Workflow Studio' });
    expect(workflow).toBeEnabled();
    await user.click(workflow);
    expect(await screen.findByText('Visual Workflow Studio')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Profesyonel' }));
    expect(screen.getByText('Bugün ne üzerinde çalışmak istiyorsunuz?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Workflow Studio Uzman/ })).toBeDisabled();
  });
});
