/**
 * T10 — the real Visual Workflow Studio user journey.
 *
 * A real Chromium drives a real production build, which talks to a real
 * `surfaces.command` process over a real socket, which persists to a real
 * SQLite file through the real Alembic-migrated schema. Nothing is
 * substituted. This is the tier ARK-REQ-0062's `e2e` column names, and the
 * only tier that can earn it: UI rendering and backend execution are two
 * views of the same C-20 graph revision, and this journey proves both sides
 * actually agree, not merely that each compiles.
 *
 * WHAT MAKES THE PERSISTENCE CLAIM REAL. The journey reloads the page, and
 * then opens a completely fresh browser context — new profile, empty
 * storage, no cookies — and finds the same published revision. Nothing
 * carried over in the browser could survive that; the graph came back from
 * the database.
 *
 * THE NEGATIVE PATH IS NOT OPTIONAL. `control.policy.WorkflowApprovalGate`
 * forbids the `workflow` actor from ever recording a HUMAN APPROVAL decision
 * (ARK-REQ-0330) — the journey asks for exactly that and requires the
 * browser to show the gate's own refusal, with the execution still paused.
 */

import { expect, test } from '@playwright/test';

const RUN = Date.now().toString(36);
const WORKFLOW_ID = `wf-e2e-${RUN}`;
const EXECUTION_ID = `exec-e2e-${RUN}`;

test.describe.configure({ mode: 'serial' });

async function openExpertStudio(page: import('@playwright/test').Page) {
  await page.getByRole('button', { name: 'Uzman', exact: true }).click();
  await page.getByRole('button', { name: 'Workflow Studio', exact: true }).click();
}

test.describe('Visual Workflow Studio journey', () => {
  test('an unpublished workflow identifier shows an honest empty canvas', async ({ page }) => {
    await page.goto('/');
    await openExpertStudio(page);

    await page.getByLabel(/workflow identifier/i).fill(WORKFLOW_ID);
    await page.getByRole('button', { name: /load latest revision/i }).click();

    await expect(page.getByText('No revision published for this identifier yet.')).toBeVisible();
    await expect(
      page.getByText('No nodes yet. Add one from the palette to begin composing a graph.'),
    ).toBeVisible();
  });

  test('a graph is composed on the canvas and published as revision 1', async ({ page }) => {
    await page.goto('/');
    await openExpertStudio(page);
    await page.getByLabel(/workflow identifier/i).fill(WORKFLOW_ID);

    // Compose: trigger -> HUMAN APPROVAL -> notification. Real drag-and-drop
    // is exercised on the trigger node so the persisted layout is not a
    // default the backend invented.
    await page.getByRole('button', { name: '+ trigger' }).click();
    const trigger = page.getByRole('button', { name: 'Workflow node trigger' });
    await trigger.scrollIntoViewIfNeeded();
    const triggerBox = await trigger.boundingBox();
    if (triggerBox === null) {
      throw new Error('trigger node did not render');
    }
    const leftBefore = await trigger.evaluate((el) => (el as HTMLElement).style.left);
    await page.mouse.move(triggerBox.x + triggerBox.width / 2, triggerBox.y + triggerBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(triggerBox.x + 90, triggerBox.y + 70, { steps: 5 });
    await page.mouse.up();
    const leftAfter = await trigger.evaluate((el) => (el as HTMLElement).style.left);
    expect(leftAfter).not.toBe(leftBefore);

    await page.getByLabel('logic').selectOption('HUMAN APPROVAL');
    await page.getByRole('button', { name: '+ logic node' }).click();
    await page.getByRole('button', { name: '+ notification' }).click();

    await page.getByRole('button', { name: 'Connect from trigger' }).click();
    await page.getByRole('button', { name: 'Workflow node HUMAN APPROVAL' }).click();
    await page.getByRole('button', { name: 'Connect from HUMAN APPROVAL' }).click();
    await page.getByRole('button', { name: 'Workflow node notification' }).click();

    await page.getByRole('button', { name: /publish revision/i }).click();

    await expect(
      page.getByText(new RegExp(`Revision 1 \\(1\\.0\\.0\\) published for ${WORKFLOW_ID}\\.`)),
    ).toBeVisible();
    await expect(page.getByText(/Revision 1 \(1\.0\.0\) · sha256:/)).toBeVisible();
  });

  test('the published revision survives a page reload', async ({ page }) => {
    await page.goto('/');
    await page.reload();
    await openExpertStudio(page);
    await page.getByLabel(/workflow identifier/i).fill(WORKFLOW_ID);
    await page.getByRole('button', { name: /load latest revision/i }).click();

    await expect(page.getByText(/Revision 1 \(1\.0\.0\)/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Workflow node trigger' })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Workflow node HUMAN APPROVAL' }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Workflow node notification' })).toBeVisible();
  });

  test('the published revision survives a completely fresh browser context', async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await page.goto('/');
      await openExpertStudio(page);
      await page.getByLabel(/workflow identifier/i).fill(WORKFLOW_ID);
      await page.getByRole('button', { name: /load latest revision/i }).click();

      await expect(page.getByText(/Revision 1 \(1\.0\.0\)/)).toBeVisible();
      await expect(page.getByRole('button', { name: 'Workflow node trigger' })).toBeVisible();

      const storage = await page.evaluate(() => ({
        local: window.localStorage.length,
        session: window.sessionStorage.length,
      }));
      expect(storage).toEqual({ local: 0, session: 0 });
    } finally {
      await context.close();
    }
  });

  test('execution pauses at HUMAN APPROVAL, refuses the workflow actor, and completes on a real approval', async ({
    page,
  }) => {
    await page.goto('/');
    await openExpertStudio(page);
    await page.getByLabel(/workflow identifier/i).fill(WORKFLOW_ID);
    await page.getByRole('button', { name: /load latest revision/i }).click();
    await expect(page.getByText(/Revision 1 \(1\.0\.0\)/)).toBeVisible();

    await page.getByLabel(/execution identifier/i).fill(EXECUTION_ID);
    await page.getByRole('button', { name: /start execution/i }).click();

    await expect(page.getByText('WAITING_APPROVAL', { exact: true })).toBeVisible();

    // THE NEGATIVE PATH. `workflow` is a named actor the canonical
    // stable-mutation policy already forbids from recording this decision.
    await page.getByLabel('Actor').fill('workflow');
    await page.getByRole('button', { name: /^approve /i }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toContainText('The operation was refused');
    await expect(alert).toContainText('ARK-ERR-0133');
    // The refusal changed nothing: still paused, waiting on the same node.
    await expect(page.getByText('WAITING_APPROVAL', { exact: true })).toBeVisible();

    await page.getByLabel('Actor').fill('human-reviewer');
    await page.getByRole('button', { name: /^approve /i }).click();

    await expect(page.getByText('SUCCEEDED', { exact: true })).toBeVisible();
    const evidenceRows = page.locator('table tbody tr');
    await expect(evidenceRows).toHaveCount(3);
    await expect(page.getByText('HUMAN_APPROVAL:awaiting')).toBeVisible();
  });
});
