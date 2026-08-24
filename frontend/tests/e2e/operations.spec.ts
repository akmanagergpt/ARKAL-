/**
 * T10 — the real Operations journey (`ARK-REQ-0396`, D-028).
 *
 * A real Chromium against a real production build and a real
 * `surfaces.command` process, exactly as `project-registry.spec.ts` -
 * see its own module docstring for what "real" means here. The snapshot
 * itself is read from the real host and the real database this backend
 * process owns; nothing here substitutes any value.
 */

import { expect, test } from '@playwright/test';

test.describe('Operations journey', () => {
  test('navigates to Operations and renders the real live snapshot', async ({ page }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const failedRequests: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => pageErrors.push(error.message));
    page.on('requestfailed', (request) => failedRequests.push(request.url()));

    await page.goto('/');
    await page.getByRole('button', { name: 'Operasyonlar', exact: true }).click();

    await expect(page.getByRole('heading', { name: 'Operasyonlar' })).toBeVisible();
    await expect(page.getByText('cpu_logical_cores')).toBeVisible();
    await expect(page.getByText('database_reachable')).toBeVisible();
    // A real, non-negative CPU core count from the real host probe - not a
    // fabricated placeholder.
    await expect(page.getByText(/^\d+$/).first()).toBeVisible();

    expect(consoleErrors).toEqual([]);
    expect(pageErrors).toEqual([]);
    expect(failedRequests).toEqual([]);
  });

  test('the manual refresh control issues a fresh read', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Operasyonlar', exact: true }).click();
    await expect(page.getByText('cpu_logical_cores')).toBeVisible();

    const [response] = await Promise.all([
      page.waitForResponse((res) => res.url().endsWith('/api/operations/snapshot')),
      page.getByRole('button', { name: 'Yenile' }).click(),
    ]);
    expect(response.status()).toBe(200);
  });

  test('the page fits the viewport with no horizontal overflow, mobile and desktop', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');
    await page.evaluate(() => {
      const button = Array.from(document.querySelectorAll('button')).find((candidate) =>
        candidate.textContent?.includes('Sistem ve çalışma durumu'),
      );
      button?.click();
    });
    await expect(page.getByText('cpu_logical_cores')).toBeVisible();

    const mobileOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(mobileOverflow).toBeLessThanOrEqual(0);

    await page.setViewportSize({ width: 1280, height: 800 });
    const desktopOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(desktopOverflow).toBeLessThanOrEqual(0);
  });

  test('keyboard navigation reaches Operations with a visible focus state', async ({ page }) => {
    await page.goto('/');
    const navButton = page.getByRole('button', { name: 'Operasyonlar', exact: true });
    await navButton.focus();
    await expect(navButton).toBeFocused();
    const outline = await navButton.evaluate((el) => getComputedStyle(el).boxShadow);
    expect(outline).not.toBe('none');

    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Operasyonlar' })).toBeVisible();
    await expect(navButton).toHaveAttribute('aria-current', 'page');
  });
});
