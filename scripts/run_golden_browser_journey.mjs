/**
 * Real Chromium journey for a generated Golden candidate, driven entirely
 * by a real `AcceptanceScenario` JSON file (`--scenario`) -- ARK-REQ-0074
 * ("Golden domain logic must not enter ARKALI core"): this script itself
 * names no resource, field, or route. What follows was hardened against
 * the Student/Fee Golden specifically; every fact that made it Student/Fee-
 * specific (routes, nav labels, field names, payload values) now comes
 * from the scenario file. The four real gaps below, and the fixes for
 * them, are domain-independent and apply to any scenario this drives.
 *
 * FOUR REAL GAPS, EACH FOUND LIVE AGAINST A REAL CANDIDATE BUILD, ARE CLOSED
 * HERE - never by relaxing what this journey actually proves.
 *
 * (1) NO ASSERTION ON A TRANSIENT "SUCCESS" TEXT. A generated candidate that
 * navigates via `window.location.href` right after a mutation (real, common,
 * unremarkable CRUD code) can unmount its own success message before the
 * browser ever paints it - it painted on one run and not on the next, an
 * inherent race against that valid pattern rather than a defect. Every
 * mutation step (create/edit/delete/related-create) already proves success
 * the same, non-racy way every other step here does: a real network
 * mutation is observed (`mutations`), and the record's new state is later
 * found in the app's own stable, reloaded view. A transient toast is a UX
 * nicety, not something this journey needs to observe to prove the
 * mutation real.
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
 *
 * (3) NO ASSUMPTION THAT EDIT LOOKS TEXTUALLY DIFFERENT FROM CREATE.
 * golden-work-113/119 (real evidence, both frozen, Student/Fee Golden): a
 * shared form component reused for both create and edit renders no "Edit"
 * heading of any kind, and its one submit button reads "Submit" on both
 * routes, not "Update"/"Save" - a real, valid, minimal implementation, not
 * a defect, and this journey's own `/update|save/i` pattern and heading
 * assertion both failed 100% of the time they were ever actually reached.
 * The heading assertion is replaced with a URL assertion (the real created
 * id's own edit route), which proves the same real fact (we reached the
 * real edit route for the real record) without presuming any particular
 * heading text exists; the submit pattern now also accepts "submit".
 *
 * (4) EDIT/DELETE NOW CLICK THE CONTROL IN THIS JOURNEY'S OWN ROW, NOT THE
 * FIRST MATCH ON THE PAGE. A fresh acceptance database can seed at least
 * one pre-existing record; `clickNamed(page, /edit/i)` would match that
 * row's Edit link first, in DOM order, silently editing the wrong record
 * every time this journey ran against a real seeded database - the PUT
 * still landed on some real id, so an unscoped mutation check (matching
 * only the collection route) never caught it. Edit/delete are scoped to
 * the list row containing this journey's own created record's own real
 * value, and both mutation checks require the exact real id this journey
 * itself created, not just any id.
 *
 * (5) A NATIVE `window.confirm()` DESTRUCTIVE-CONFIRMATION IS A REAL, VALID
 * IMPLEMENTATION CHOICE, NOT A DEFECT. golden-work-127 (real evidence,
 * frozen): its own real Students.js wires the row's own "Delete" button
 * directly to `if (window.confirm(...)) { await deleteStudent(id); ... }`
 * - no separate confirm route or in-page Yes/No control exists at all, the
 * one real, idiomatic pattern this journey had not yet seen. Playwright
 * auto-DISMISSES any dialog with no registered handler (`confirm()`
 * resolves `false`), so the click fired, the dialog appeared and was
 * silently dismissed, and the `if` branch - and therefore the real DELETE
 * request - never ran: "delete flow did not emit a real DELETE .../9
 * request", reproduced live. A human clicking the same button in a real
 * browser sees the dialog and can accept it; this journey must do the
 * same rather than penalizing a candidate for a real, common React
 * pattern. The handler below accepts every dialog unconditionally - this
 * journey drives no destructive action it does not itself intend, so
 * there is nothing to decline.
 */

import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
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
const primaryIdIndex = process.argv.indexOf('--primary-id');
const primaryBackendId = primaryIdIndex >= 0 ? process.argv[primaryIdIndex + 1] : null;
if (!primaryBackendId || !/^\d+$/.test(primaryBackendId)) {
  throw new Error('--primary-id must identify the real backend-persisted primary record');
}
const scenarioIndex = process.argv.indexOf('--scenario');
const scenarioPath = scenarioIndex >= 0 ? process.argv[scenarioIndex + 1] : null;
if (!scenarioPath) {
  throw new Error('--scenario must name a real AcceptanceScenario JSON file');
}
const scenario = JSON.parse(readFileSync(scenarioPath, 'utf-8'));
const resourceByName = Object.fromEntries(scenario.resources.map((r) => [r.name, r]));
const primary = resourceByName[scenario.primary_resource];
const related = scenario.related_resource ? resourceByName[scenario.related_resource] : null;
const dashboardLabel = scenario.navigation_destinations[scenario.navigation_destinations.length - 1];

/** A loose, case-insensitive label pattern for a real declared field name
 * -- "due_date" -> /due.*date/i, "amount" -> /amount/i -- the same shape
 * this journey's own hardened patterns already used before every field
 * name was a scenario value rather than a literal. */
function fieldPattern(fieldName) {
  return new RegExp(fieldName.replace(/_/g, '.*'), 'i');
}

function navPattern(label) {
  return new RegExp(label, 'i');
}

function createButtonPattern(singularLabel) {
  const word = singularLabel.toLowerCase();
  return new RegExp(`create.*${word}|add.*${word}|new.*${word}`, 'i');
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

async function fillFields(page, fields, values) {
  for (const fieldName of fields) {
    if (Object.prototype.hasOwnProperty.call(values, fieldName)) {
      await fillByLabel(page, fieldPattern(fieldName), String(values[fieldName]));
    }
  }
}

/** The `pattern`-named control inside the list row whose text is `rowText`. */
async function clickInRow(page, rowText, pattern) {
  const row = page.getByRole('listitem').filter({ hasText: rowText });
  const control = await firstVisible([
    row.getByRole('link', { name: pattern }),
    row.getByRole('button', { name: pattern }),
  ]);
  await control.click();
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];
const mutations = [];
page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
page.on('pageerror', (error) => pageErrors.push(String(error)));
// (5, module docstring): a real destructive-confirmation can be a native
// `window.confirm()`, which Playwright otherwise auto-dismisses. Accepting
// every dialog is what a real user proceeding through this journey does.
page.on('dialog', (dialog) => { void dialog.accept(); });
page.on('requestfailed', (request) => failedRequests.push(`${request.method()} ${request.url()}`));
page.on('response', (response) => {
  const method = response.request().method();
  if (!response.url().startsWith(API) || !['POST', 'PUT', 'DELETE'].includes(method)) return;
  mutations.push({ method, url: response.url(), status: response.status() });
});

try {
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await expect(page.getByRole('navigation')).toBeVisible();
  await clickNamed(page, navPattern(primary.navigation_label));
  await expect(page.getByRole('heading', { name: navPattern(primary.navigation_label) })).toBeVisible();

  const createValues = scenario.browser_create_values || {};
  await clickNamed(page, createButtonPattern(primary.singular_label));
  for (const fieldName of primary.editable_form_fields) {
    await expect(page.getByLabel(fieldPattern(fieldName))).toBeVisible();
  }
  const mutationCountBeforeValidation = mutations.length;
  await clickNamed(page, new RegExp(`create.*${primary.singular_label.toLowerCase()}|save|submit`, 'i'));
  if (mutations.length !== mutationCountBeforeValidation) {
    throw new Error('invalid empty form emitted a network mutation');
  }
  await fillFields(page, primary.editable_form_fields, createValues);
  await clickNamed(page, new RegExp(`create.*${primary.singular_label.toLowerCase()}|save|submit`, 'i'));
  await waitForMutation(
    mutations,
    (m) => m.method === 'POST' && m.url.includes(primary.collection_route),
    `${primary.name} form did not emit a real POST ${primary.collection_route} request`,
  );

  const createdText = Object.values(createValues)[0];
  await clickNamed(page, navPattern(primary.navigation_label));
  await expect(page.getByText(createdText, { exact: false })).toBeVisible();
  // Read the real created id back from the list's own rendered edit link
  // (its href always embeds the record's real id) rather than the create
  // POST's response body: that read raced against a real candidate's own
  // window.location.href navigation and intermittently came back empty,
  // reproduced live against the Student/Fee Golden - the DOM here is
  // post-navigation and stable.
  const createdRow = page.getByRole('listitem').filter({ hasText: createdText });
  const editHref = await createdRow.getByRole('link', { name: /edit/i }).first().getAttribute('href');
  const createdIdMatch = editHref?.match(/(\d+)\/?$/);
  if (!createdIdMatch) {
    throw new Error(`the new ${primary.name} row has no numeric id in its edit link href: ${editHref}`);
  }
  const createdId = createdIdMatch[1];
  await clickInRow(page, createdText, /edit/i);
  const collectionSegment = primary.collection_route.replace(/^\//, '');
  await expect(page).toHaveURL(new RegExp(`/${collectionSegment}/edit/${createdId}(?:[/?]|$)`));
  const updateValues = scenario.browser_update_values || {};
  await fillFields(page, primary.editable_form_fields, updateValues);
  await clickNamed(page, /update|save|submit/i);
  await waitForMutation(
    mutations,
    (m) => m.method === 'PUT' && m.url.includes(`${primary.collection_route}/${createdId}`),
    `edit form did not emit a real PUT ${primary.collection_route}/${createdId} request`,
  );

  const updatedText = Object.values(updateValues)[0] || createdText;
  await clickNamed(page, navPattern(primary.navigation_label));
  await expect(page.getByText(updatedText, { exact: false })).toBeVisible();
  await clickInRow(page, updatedText, /delete/i);
  const confirm = await firstVisible([
    page.getByRole('button', { name: /confirm|yes|delete/i }),
    page.getByRole('link', { name: /confirm|yes|delete/i }),
  ]);
  await confirm.click();
  await waitForMutation(
    mutations,
    (m) => m.method === 'DELETE' && m.url.includes(`${primary.collection_route}/${createdId}`),
    `delete flow did not emit a real DELETE ${primary.collection_route}/${createdId} request`,
  );

  if (related) {
    await clickNamed(page, navPattern(related.navigation_label));
    await expect(page.getByRole('heading', { name: navPattern(related.navigation_label) })).toBeVisible();
    const relatedCreate = page.getByRole('link', { name: createButtonPattern(related.singular_label) });
    if (await relatedCreate.count()) {
      await relatedCreate.first().click();
      const relationshipField = Object.keys(related.relationship_fields || {})[0];
      if (relationshipField) {
        await fillByLabel(page, fieldPattern(relationshipField), primaryBackendId);
      }
      await fillFields(page, related.editable_form_fields, scenario.browser_related_values || {});
      await clickNamed(page, new RegExp(`create.*${related.singular_label.toLowerCase()}|save|submit`, 'i'));
      await waitForMutation(
        mutations,
        (m) => m.method === 'POST' && m.url.includes(related.collection_route),
        `${related.name} form did not emit a real POST ${related.collection_route} request`,
      );
    }
  }

  await clickNamed(page, navPattern(dashboardLabel));
  await expect(page.getByRole('heading', { name: navPattern(dashboardLabel) })).toBeVisible();
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
