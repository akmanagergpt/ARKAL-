/**
 * T10 — the real Project Registry user journey.
 *
 * A real Chromium drives a real production build, which talks to a real
 * `surfaces.command` process over a real socket, which persists to a real
 * SQLite file through the real Alembic-migrated schema. Nothing is substituted.
 * This is the tier the register's `e2e` column names for ARK-REQ-0178 and
 * ARK-REQ-0229, and the only tier that can earn it.
 *
 * WHAT MAKES THE PERSISTENCE CLAIM REAL. The journey reloads the page, and then
 * opens a **completely fresh browser context** — new profile, empty storage, no
 * cookies — and finds the same project. Nothing carried over in the browser
 * could survive that; the state came back from the database.
 *
 * THE NEGATIVE PATH IS NOT OPTIONAL. A UI that shows only successes proves
 * nothing about where authority lives. The journey asks for a transition the
 * Project machine forbids and requires the browser to show the machine's own
 * refusal, with the stored state unchanged.
 */

import { expect, test } from '@playwright/test';

// One id per run, so a journey never depends on — or collides with — another.
const RUN = Date.now().toString(36);
const PROJECT_ID = `prj-e2e-${RUN}`;
const PROJECT_NAME = `E2E Programme ${RUN}`;
const REVISION_ID = `rev-e2e-${RUN}`;

test.describe.configure({ mode: 'serial' });

test.describe('Project Registry journey', () => {
  test('the empty registry is presented honestly', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Project Registry' })).toBeVisible();
    await expect(page.getByText('No projects yet')).toBeVisible();
  });

  test('a project is created and appears in the registry', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('No projects yet')).toBeVisible();

    await page.getByLabel(/project identifier/i).fill(PROJECT_ID);
    await page.getByLabel(/project name/i).fill(PROJECT_NAME);
    await page.getByRole('button', { name: /register project/i }).click();

    await expect(page.getByText(/registered in DRAFT/i)).toBeVisible();
    await expect(page.getByRole('list').getByText(PROJECT_NAME)).toBeVisible();
  });

  test('the detail view shows the project the backend recorded', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('list').getByText(PROJECT_NAME).click();

    const detail = page.locator('section', { hasText: 'Project detail' });
    await expect(detail.getByText(PROJECT_ID)).toBeVisible();
    await expect(detail.locator('header')).toContainText('DRAFT');
    await expect(detail.getByText('No revisions recorded for this project yet.')).toBeVisible();
  });

  test('a revision is recorded and rendered', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('list').getByText(PROJECT_NAME).click();

    await page.getByLabel(/new revision identifier/i).fill(REVISION_ID);
    await page.getByRole('button', { name: /record revision/i }).click();

    await expect(page.getByText(new RegExp(`Revision ${REVISION_ID} recorded`))).toBeVisible();
    const row = page.getByRole('row', { name: new RegExp(REVISION_ID) });
    await expect(row).toBeVisible();
    // The sequence the registry assigned. Matched as an exact cell, because the
    // generated revision id also contains digits.
    await expect(row.getByRole('cell', { name: '1', exact: true })).toBeVisible();
  });

  test('a forbidden transition is refused by the machine, not by the browser', async ({
    page,
  }) => {
    await page.goto('/');
    await page.getByRole('list').getByText(PROJECT_NAME).click();

    // DRAFT -> ACTIVE is declared forbidden by the canonical Project machine.
    // The option is offered anyway: the browser holds no transition relation
    // and is not entitled to decide this.
    await page.getByLabel(/requested state/i).selectOption('ACTIVE');
    await page.getByRole('button', { name: /request transition/i }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toContainText('The operation was refused');
    await expect(alert).toContainText('DRAFT->ACTIVE is explicitly forbidden');
    await expect(alert).toContainText('ARK-ERR-0013');

    // The refusal changed nothing. Asserted against the displayed state badge,
    // not against the absence of the word: `ACTIVE` is still present on the
    // page as a `<select>` option, and that is the design — the browser offers
    // every state the machine declares because it is not entitled to filter
    // them. Scoping to the badge is what distinguishes "shown as offered" from
    // "shown as the project's state".
    const state = page.locator('section', { hasText: 'Project detail' }).locator('header');
    await expect(state).toContainText('DRAFT');
    await expect(state).not.toContainText('ACTIVE');
  });

  test('a duplicate registration is refused with the backend reason', async ({ page }) => {
    await page.goto('/');
    await page.getByLabel(/project identifier/i).fill(PROJECT_ID);
    await page.getByLabel(/project name/i).fill('A Different Name');
    await page.getByRole('button', { name: /register project/i }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toContainText('already registered');
    await expect(alert).toContainText('ARK-ERR-0012');
  });

  test('a legal transition is accepted and the new state is displayed', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('list').getByText(PROJECT_NAME).click();

    await page.getByLabel(/requested state/i).selectOption('SPECIFIED');
    await page.getByRole('button', { name: /request transition/i }).click();

    await expect(page.getByText(`${PROJECT_ID} is now SPECIFIED.`)).toBeVisible();
    await expect(page.getByRole('list').getByText('SPECIFIED')).toBeVisible();
  });

  test('the state survives a page reload', async ({ page }) => {
    await page.goto('/');
    await page.reload();

    const row = page.getByRole('list').getByText(PROJECT_NAME);
    await expect(row).toBeVisible();
    await row.click();

    const detail = page.locator('section', { hasText: 'Project detail' });
    await expect(detail.locator('header')).toContainText('SPECIFIED');
    await expect(detail.getByRole('row', { name: new RegExp(REVISION_ID) })).toBeVisible();
  });

  test('the state survives a completely fresh browser context', async ({ browser }) => {
    // A new context has its own profile: no localStorage, no sessionStorage, no
    // cookies, no in-memory state from any earlier test. If the project is
    // still here, it came back from the database and from nowhere else.
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await page.goto('/');
      await page.getByRole('list').getByText(PROJECT_NAME).click();

      const detail = page.locator('section', { hasText: 'Project detail' });
      await expect(detail.getByText(PROJECT_ID)).toBeVisible();
      await expect(detail.locator('header')).toContainText('SPECIFIED');
      await expect(detail.getByRole('row', { name: new RegExp(REVISION_ID) })).toBeVisible();

      const storage = await page.evaluate(() => ({
        local: window.localStorage.length,
        session: window.sessionStorage.length,
      }));
      expect(storage).toEqual({ local: 0, session: 0 });
    } finally {
      await context.close();
    }
  });
});
