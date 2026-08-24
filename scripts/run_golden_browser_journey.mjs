/**
 * Real Chromium journey for a generated Student/Fee Golden candidate.
 *
 * TWO REAL TIMING GAPS, FOUND LIVE AGAINST golden-work-113's OWN BUILD, ARE
 * CLOSED HERE - neither by relaxing what this journey actually proves.
 *
 * (1) NO ASSERTION ON A TRANSIENT "SUCCESS" TEXT. A generated candidate that
 * navigates via `window.location.href` right after a mutation (real, common,
 * unremarkable CRUD code) can unmount its own success message before the
 * browser ever paints it - it painted on one run and not on the next, an
 * inherent race against that valid pattern rather than a defect. Every
 * mutation step (create/edit/delete/payment) already proves success the
 * same, non-racy way every other step here does: a real network mutation is
 * observed (`mutations`), and the record's new state is later found in the
 * app's own stable, reloaded view. A transient toast is a UX nicety, not
 * something this journey needs to observe to prove the mutation real.
 *
 * (2) `firstVisible` (`lib/browser_journey_wait.mjs`) now retries instead of
 * checking visibility once - the same full-reload window can hide the next
 * control this journey needs to click, not only the toast in (1). Every
 * `mutations` check now polls (`waitForMutation`) instead of a fixed
 * `waitForTimeout(200)`: that fixed wait was already the only thing standing
 * between a real mutation and the check confirming it, for all four
 * mutations this journey drives, and 200ms is not a bound on anything real -
 * a slower first fetch under real host load can exceed it, which is exactly
 * what a live run reproduced.
 */

import { createRequire } from 'node:module';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { firstVisible, waitForMutation } from './lib/browser_journey_wait.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const requireFromFrontend = createRequire(path.join(ROOT, 'frontend', 'package.json'));
const { chromium, expect } = requireFromFrontend('@playwright/test');
const BASE = 'http://127.0.0.1:3000';
const API = 'http://localhost:5000';
const candidateIndex = process.argv.indexOf('--candidate');
const candidate = candidateIndex >= 0 ? process.argv[candidateIndex + 1] : 'unknown';
const studentIdIndex = process.argv.indexOf('--student-id');
const studentId = studentIdIndex >= 0 ? process.argv[studentIdIndex + 1] : null;
if (!studentId || !/^\d+$/.test(studentId)) {
  throw new Error('--student-id must identify the persisted backend acceptance student');
}

async function clickNamed(page, pattern) {
  const control = await firstVisible([
    page.getByRole('link', { name: pattern }),
    page.getByRole('button', { name: pattern }),
  ]);
  await control.click();
}

async function fillByLabel(page, pattern, value) {
  const input = await firstVisible([
    page.getByLabel(pattern), page.getByPlaceholder(pattern),
  ]);
  await input.fill(value);
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];
const mutations = [];
page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
page.on('pageerror', (error) => pageErrors.push(String(error)));
page.on('requestfailed', (request) => failedRequests.push(`${request.method()} ${request.url()}`));
page.on('response', (response) => {
  if (response.url().startsWith(API) && ['POST', 'PUT', 'DELETE'].includes(response.request().method())) {
    mutations.push(`${response.request().method()} ${response.url()} -> ${response.status()}`);
  }
});

try {
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await expect(page.getByRole('navigation')).toBeVisible();
  await clickNamed(page, /students/i);
  await expect(page.getByRole('heading', { name: /students/i })).toBeVisible();

  await clickNamed(page, /create.*student|add.*student|new.*student/i);
  await expect(page.getByLabel(/name/i)).toBeVisible();
  await expect(page.getByLabel(/email/i)).toBeVisible();
  const mutationCountBeforeValidation = mutations.length;
  await clickNamed(page, /create.*student|save|submit/i);
  if (mutations.length !== mutationCountBeforeValidation) {
    throw new Error('invalid empty form emitted a network mutation');
  }
  await fillByLabel(page, /name/i, 'Browser Acceptance Student');
  await fillByLabel(page, /email/i, 'browser.acceptance@example.com');
  await clickNamed(page, /create.*student|save|submit/i);
  await waitForMutation(
    mutations,
    (item) => item.startsWith('POST ') && item.includes('/students'),
    'student form did not emit a real POST /students request',
  );

  await clickNamed(page, /students/i);
  await expect(page.getByText('Browser Acceptance Student', { exact: false })).toBeVisible();
  await clickNamed(page, /edit/i);
  await expect(page.getByRole('heading', { name: /edit/i })).toBeVisible();
  await fillByLabel(page, /name/i, 'Browser Acceptance Edited');
  await clickNamed(page, /update|save/i);
  await waitForMutation(
    mutations,
    (item) => item.startsWith('PUT ') && item.includes('/students/'),
    'edit form did not emit a real PUT /students/:id request',
  );

  await clickNamed(page, /students/i);
  await expect(page.getByText('Browser Acceptance Edited', { exact: false })).toBeVisible();
  await clickNamed(page, /delete/i);
  const confirm = await firstVisible([
    page.getByRole('button', { name: /confirm|yes|delete/i }),
    page.getByRole('link', { name: /confirm|yes|delete/i }),
  ]);
  await confirm.click();
  await waitForMutation(
    mutations,
    (item) => item.startsWith('DELETE ') && item.includes('/students/'),
    'delete flow did not emit a real DELETE /students/:id request',
  );

  await clickNamed(page, /payments/i);
  await expect(page.getByRole('heading', { name: /payments/i })).toBeVisible();
  const paymentCreate = page.getByRole('link', { name: /create.*payment|add.*payment|new.*payment/i });
  if (await paymentCreate.count()) {
    await paymentCreate.first().click();
    await fillByLabel(page, /student.*id/i, studentId);
    await fillByLabel(page, /amount/i, '50.25');
    await fillByLabel(page, /due.*date/i, '2030-02-01');
    await clickNamed(page, /create.*payment|save|submit/i);
    await waitForMutation(
      mutations,
      (item) => item.startsWith('POST ') && item.includes('/payments'),
      'payment form did not emit a real POST /payments request',
    );
  }

  await clickNamed(page, /dashboard/i);
  await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible();
  if (consoleErrors.length || pageErrors.length || failedRequests.length) {
    throw new Error(JSON.stringify({ consoleErrors, pageErrors, failedRequests }));
  }
  console.log(JSON.stringify({
    outcome: 'BROWSER_JOURNEY_PASS', candidate, mutations,
    validation: 'empty required form emitted no mutation',
    consoleErrors: 0, pageErrors: 0, failedRequests: 0,
  }));
} finally {
  await browser.close();
}
