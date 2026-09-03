/**
 * The Project Registry slice, rendered.
 *
 * NOT A BROWSER TEST. This is jsdom with React Testing Library — a component
 * and integration tier. T10 browser/E2E is NOT_CONFIGURED and nothing here may
 * be reported as it.
 *
 * The whole application is mounted against the real `ArkaliApiClient`; only the
 * network beneath it is controlled. Every assertion below therefore exercises
 * the production request-building, status-interpretation and refresh paths.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';
import { ArkaliApiClient } from '@/api/client';
import { projectStateLabel } from '@/components/ui';
import {
  DRAFT_PROJECT,
  EMPTY_LIST,
  LIFECYCLE,
  SPECIFIED_PROJECT,
  listOf,
  stubFetch,
} from '../fixtures';

const BASE = 'http://127.0.0.1:8000';
const LIST = `GET ${BASE}/api/projects`;
const CREATE = `POST ${BASE}/api/projects`;
const LIFECYCLE_ROUTE = `GET ${BASE}/api/lifecycle/project`;
const DETAIL = `GET ${BASE}/api/projects/prj-alpha`;
const TRANSITION = `POST ${BASE}/api/projects/prj-alpha/transitions`;

const lifecycleRoute = { status: 200, body: LIFECYCLE };

function mount(routes: Parameters<typeof stubFetch>[0]) {
  const { fetchImpl, calls } = stubFetch(routes);
  const client = new ArkaliApiClient({ baseUrl: BASE, fetchImpl });
  const rendered = render(<App client={client} />);
  fireEvent.click(screen.getByRole('button', { name: 'Yönetilen Ürünler' }));
  return { ...rendered, calls };
}

describe('Project Registry page', () => {
  it('shows a loading state before the registry answers', async () => {
    mount({ [LIST]: { status: 200, body: EMPTY_LIST }, [LIFECYCLE_ROUTE]: lifecycleRoute });

    expect(screen.getByText('Uygulamalar yükleniyor…')).toBeInTheDocument();
    // Let both in-flight reads settle so the assertion above is about the
    // loading state itself, not about a race the next test would inherit.
    await screen.findByText('Henüz uygulama yok');
  });

  it('shows a useful empty state when no project is registered', async () => {
    mount({ [LIST]: { status: 200, body: EMPTY_LIST }, [LIFECYCLE_ROUTE]: lifecycleRoute });

    expect(await screen.findByText('Henüz uygulama yok')).toBeInTheDocument();
    expect(screen.getByText(/ARKALI veritabanında tutulur/i)).toBeInTheDocument();
  });

  it('renders a real backend response shape', async () => {
    mount({
      [LIST]: { status: 200, body: listOf(DRAFT_PROJECT) },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    expect(await screen.findByText('Alpha Programme')).toBeInTheDocument();
    expect(screen.queryByText('prj-alpha')).not.toBeInTheDocument();
    expect(screen.getByText(projectStateLabel('DRAFT'))).toBeInTheDocument();
  });

  it('presents a backend failure instead of an empty registry', async () => {
    mount({ [LIST]: { status: 500, body: {} }, [LIFECYCLE_ROUTE]: lifecycleRoute });

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Kayıtlar okunamadı')).toBeInTheDocument();
    expect(screen.queryByText('Henüz uygulama yok')).not.toBeInTheDocument();
  });

  it('creates a project and refreshes the list from the backend', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [LIST]: [
        { status: 200, body: EMPTY_LIST },
        { status: 200, body: listOf(DRAFT_PROJECT) },
      ],
      [CREATE]: { status: 201, body: DRAFT_PROJECT },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    await screen.findByText('Henüz uygulama yok');
    await user.type(screen.getByLabelText(/uygulama adı/i), 'Alpha Programme');
    await user.click(screen.getByRole('button', { name: /uygulamayı ekle/i }));

    expect(await screen.findByText(/kaydedildi/i)).toBeInTheDocument();
    // The list was re-read from the backend, so the new project is in it.
    await waitFor(() =>
      expect(within(screen.getByRole('list')).getByText('Alpha Programme')).toBeInTheDocument(),
    );
    expect(calls.filter((call) => call.url.endsWith('/api/projects') && call.method === 'GET'))
      .toHaveLength(2);
    const createCall = calls.find((call) => call.method === 'POST');
    expect((createCall?.body as { name: string }).name).toBe('Alpha Programme');
    expect((createCall?.body as { project_id: string }).project_id).toMatch(/^alpha-programme-/);
  });

  it('refuses to submit a blank registration and says why', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [LIST]: { status: 200, body: EMPTY_LIST },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    await screen.findByText('Henüz uygulama yok');
    await user.click(screen.getByRole('button', { name: /uygulamayı ekle/i }));

    expect(await screen.findByText('Bir ad girmelisiniz.')).toBeInTheDocument();
    expect(calls.some((call) => call.method === 'POST')).toBe(false);
  });

  it('reports a refused creation with the backend code and message', async () => {
    const user = userEvent.setup();
    mount({
      [LIST]: { status: 200, body: EMPTY_LIST },
      [CREATE]: {
        status: 409,
        body: { detail: { code: 'DUPLICATE_IDENTITY', message: 'prj-alpha already exists' } },
      },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    await screen.findByText('Henüz uygulama yok');
    await user.type(screen.getByLabelText(/uygulama adı/i), 'Alpha Programme');
    await user.click(screen.getByRole('button', { name: /uygulamayı ekle/i }));

    expect(await screen.findByText('prj-alpha already exists')).toBeInTheDocument();
    expect(screen.getByText('DUPLICATE_IDENTITY')).toBeInTheDocument();
  });

  it('loads the selected project with its revisions', async () => {
    const user = userEvent.setup();
    mount({
      [LIST]: { status: 200, body: listOf(SPECIFIED_PROJECT) },
      [DETAIL]: { status: 200, body: SPECIFIED_PROJECT },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    await user.click(await screen.findByText('Alpha Programme'));

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getByText('Sürüm 1')).toBeInTheDocument();
  });

  it('offers every declared state and lets the backend decide legality', async () => {
    const user = userEvent.setup();
    mount({
      [LIST]: { status: 200, body: listOf(DRAFT_PROJECT) },
      [DETAIL]: { status: 200, body: DRAFT_PROJECT },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    await user.click(await screen.findByText('Alpha Programme'));
    const select = await screen.findByLabelText(/yeni durum/i);

    // Every state the machine declares is offered, including ones that are not
    // reachable from DRAFT. Filtering them here would be a second authority.
    for (const state of LIFECYCLE.states) {
      expect(
        within(select).getByRole('option', { name: projectStateLabel(state) }),
      ).toBeInTheDocument();
    }
  });

  it('completes a legal transition and shows the new state from the response', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [LIST]: [
        { status: 200, body: listOf(DRAFT_PROJECT) },
        { status: 200, body: listOf(SPECIFIED_PROJECT) },
      ],
      [DETAIL]: { status: 200, body: DRAFT_PROJECT },
      [TRANSITION]: { status: 200, body: SPECIFIED_PROJECT },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    await user.click(await screen.findByText('Alpha Programme'));
    await user.selectOptions(await screen.findByLabelText(/yeni durum/i), 'SPECIFIED');
    await user.click(screen.getByRole('button', { name: /durumu değiştir/i }));

    expect(
      await screen.findByText(`prj-alpha artık ${projectStateLabel('SPECIFIED')} durumunda.`),
    ).toBeInTheDocument();
    expect(calls.find((call) => call.url.endsWith('/transitions'))?.body).toEqual({
      target: 'SPECIFIED',
    });
    await waitFor(() =>
      expect(screen.getAllByText(projectStateLabel('SPECIFIED')).length).toBeGreaterThan(0),
    );
  });

  it("shows the machine's own refusal when a transition is illegal", async () => {
    const user = userEvent.setup();
    mount({
      [LIST]: { status: 200, body: listOf(DRAFT_PROJECT) },
      [DETAIL]: { status: 200, body: DRAFT_PROJECT },
      [TRANSITION]: {
        status: 409,
        body: {
          detail: {
            code: 'FORBIDDEN_TRANSITION',
            message: 'Project: DRAFT -> ACTIVE is forbidden',
          },
        },
      },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    await user.click(await screen.findByText('Alpha Programme'));
    await user.selectOptions(await screen.findByLabelText(/yeni durum/i), 'ACTIVE');
    await user.click(screen.getByRole('button', { name: /durumu değiştir/i }));

    expect(await screen.findByText('Project: DRAFT -> ACTIVE is forbidden')).toBeInTheDocument();
    expect(screen.getByText('FORBIDDEN_TRANSITION')).toBeInTheDocument();
    // The displayed state is unchanged: the refusal did not mutate the view.
    expect(screen.getAllByText(projectStateLabel('DRAFT')).length).toBeGreaterThan(0);
  });

  it('offers no lifecycle action when the vocabulary cannot be read', async () => {
    const user = userEvent.setup();
    mount({
      [LIST]: { status: 200, body: listOf(DRAFT_PROJECT) },
      [DETAIL]: { status: 200, body: DRAFT_PROJECT },
      [LIFECYCLE_ROUTE]: { status: 500, body: {} },
    });

    await user.click(await screen.findByText('Alpha Programme'));

    expect(await screen.findByText('Durum listesi alınamadı')).toBeInTheDocument();
    expect(screen.queryByLabelText(/yeni durum/i)).not.toBeInTheDocument();
  });

  it('re-reads the registry when refresh is pressed', async () => {
    const user = userEvent.setup();
    const { calls } = mount({
      [LIST]: { status: 200, body: EMPTY_LIST },
      [LIFECYCLE_ROUTE]: lifecycleRoute,
    });

    await screen.findByText('Henüz uygulama yok');
    await user.click(screen.getByRole('button', { name: /yenile/i }));

    await waitFor(() =>
      expect(calls.filter((call) => call.method === 'GET' && call.url.endsWith('/api/projects')))
        .toHaveLength(2),
    );
  });
});
