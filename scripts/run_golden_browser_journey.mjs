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
 * SIX REAL GAPS, EACH FOUND LIVE AGAINST A REAL CANDIDATE BUILD, ARE CLOSED
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
 *
 * (6) A VISIBLE PAGE HEADING IS NOT A CANONICAL REQUIREMENT OF A ROUTABLE
 * PAGE. golden-work-128 (real evidence, frozen): its own real `Payments.js`
 * and `Courses.js` are both real, correct, reachable read-only views -- a
 * real `<Link to='/payments'>`, a real `<Route>`, real rendered content --
 * with no heading element of any kind, the same real, valid, minimal
 * implementation choice gap 3 already established for an edit page's own
 * missing heading. Neither `ARK-REQ-0072`/`0311`/`0312` nor
 * `STAGED_GENERATION_STAGES.md#8` ("every declared navigation destination
 * ... must be reachable through a real navigation element or a real
 * interactive control") names a heading, an ARIA role, or any page-identity
 * text; `frontend_ux_preflight.py`'s own structural reachability check
 * (`_navigation_reconciliation_findings`) already, deliberately, checks
 * only that the nav label's text appears somewhere in the frontend, not
 * that a heading exists -- this journey's own three heading assertions
 * (primary/related/dashboard) were strictly stronger than every layer
 * above them, unbacked by any of them. Human governance decision (session
 * record): a page heading is required only when a goal/spec/requirement or
 * the candidate's own declared acceptance contract requires one -- it is
 * not ARKALI's general product invariant. Replaced with
 * `navigateAndVerifyReachable` (`lib/browser_journey_wait.mjs`): reads the
 * real `href` the candidate's own nav control declares, clicks it, and
 * proves the browser's own URL actually transitioned to that real path --
 * declared route -> real navigation -> observed URL, nothing about the
 * destination page's content is assumed. A control with no `href` (a
 * `<button>` driving `history.push`) is verified by a real URL change
 * instead, since no further real fact exists to check it against.
 *
 * (7) DECLARED-MANDATORY CAPABILITIES MUST NEVER SILENTLY SKIP, AND EDIT
 * MUST BE PROVEN TO SHOW REAL DATA BEFORE IT IS OVERWRITTEN. A real ARKALI
 * LIVE PRODUCT CHECKPOINT (golden-work-129, historical specimen, real
 * evidence -- not a rule about that one product) found two real, distinct
 * measurement-truth gaps in this journey itself, neither a defect in the
 * candidate this journey was driving:
 *   (a) the related-resource create step below used to run only
 *   `if (await relatedCreate.count())` -- a genuinely MISSING create
 *   control for a resource whose own `_AcceptanceScenario.actions`
 *   (`acceptance_plan_compiler.py`'s own real, spec+backend-reconciled
 *   result -- never guessed here) already, mechanically declares "create"
 *   produced no failure at all, just a silently skipped verification
 *   block. `golden-work-129`'s own real `Payments.js` has exactly this
 *   shape: `apiClient.js` exports a real, working `createPayment`, the
 *   real backend genuinely accepts `POST /payments`, and no UI control
 *   anywhere calls either -- a real, reachable, but entirely unexercised
 *   capability gap this journey's own old guard let straight through.
 *   (b) the edit step below filled the form with `browser_update_values`
 *   and asserted only the POST-mutation result -- never reading what the
 *   form showed BEFORE typing. `golden-work-129`'s own real `StudentForm`
 *   accepts an `initialData` prop its caller passes but never reads it
 *   inside the component -- the edit form silently renders blank on every
 *   real load. A journey that only checks the post-submit result cannot
 *   tell "the form was correctly pre-filled, then edited" from "the form
 *   was blank, then filled from scratch" -- both produce an identical PUT
 *   and an identical post-submit list. Only reading the form's own real
 *   values before this journey types anything new can distinguish them.
 * The fix for both is the same real invariant, never a per-product
 * special case: a spec+backend-declared MANDATORY capability's own
 * observable (a control, a pre-filled value) must genuinely exist and be
 * exercised -- SKIP is legitimate only for a capability neither the
 * candidate's own `product_ux_spec.json` nor its own real backend routes
 * ever declared.
 *
 * (8) CAPABILITY-AWARE ACCEPTANCE (human governance decision, session
 * record): a primary resource whose own real, reconciled `actions` (the
 * same `_ResourceScenario.actions` this journey already reads for gap 7)
 * never declares "create"/"edit" at all is a legitimate, real READ-ONLY
 * product shape (real evidence: `factory-goal-mtquvzmc-dt3go3`, a real
 * library-overdue-books reporting view) -- never a defect, and never a
 * reason to synthesize a create/edit/delete flow this journey was never
 * asked to prove. Such a primary never produces a real backend id, so
 * `--primary-id` is no longer unconditionally required; it stays required
 * only for a mutation-capable primary. The read-only journey below proves
 * the one real, observable fact its own declared capability actually
 * promises: real navigation to its own destination succeeds, with no
 * console/page/network error -- reusing this file's own existing
 * `navigateTo`/`navigateAndVerifyReachable` primitives, never a second
 * journey engine.
 *
 * (9) A NAVIGATION LANDMARK IS NOT A CANONICAL REQUIREMENT OF A GENUINELY
 * SINGLE-VIEW PRODUCT. Real evidence, `factory-goal-mtr3en0w-a3xa19` (the
 * first real candidate this session's own capability-aware read-only
 * acceptance actually reached the real browser journey against, F-0090's
 * own fix having just unblocked the frontend build step that used to fail
 * first): its own real `product_ux_spec.json` declares exactly ONE
 * navigation destination ("Overdue Books"), and its own real, valid,
 * minimal frontend (`ReactDOM.render(<OverdueBooks />, ...)`, no router,
 * no nav bar) renders that content directly at the app's own root URL --
 * the only real, observable page this product was ever asked to have.
 * This journey's own unconditional `getByRole('navigation')` visibility
 * assertion, gap 6's own real evidence already having established that a
 * heading is not a canonical requirement, made the identical mistake one
 * landmark over: neither `ARK-REQ-0072`/`0311`/`0312` nor
 * `STAGED_GENERATION_STAGES.md#8` names a `<nav>` element or an ARIA
 * `navigation` role for a product with nothing to navigate BETWEEN, and a
 * real, live `ExpectError: locator.toBeVisible() ... getByRole('navigation')`
 * timeout reproduced this exactly, on a candidate whose own real backend
 * install, tests, read-only journey (`overdue_books_read`, `read_only_
 * restart_recovery`) and frontend production build had all already,
 * genuinely PASSED. `scenario.navigation_destinations.length === 1` is the
 * same real, declared-intent signal already used everywhere else in this
 * file (never a route name, never a candidate-specific string): when
 * true, `dashboardLabel` degenerates to `primary.navigation_label` itself
 * -- there is no second destination to click FROM the first -- so the
 * initial nav-landmark check, the initial `navigateTo(primary)` (already
 * on it, by definition, the instant `BASE` loads) and the final
 * `navigateTo(dashboardLabel)` are all real no-ops for this shape, and are
 * skipped rather than demanding UI this pipeline's own real, valid intent
 * never asked the candidate to build.
 */

import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { firstVisible, navigateAndVerifyReachable, waitForMutation } from './lib/browser_journey_wait.mjs';

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
// (9, module docstring): a scenario declaring exactly ONE real navigation
// destination has nothing to navigate BETWEEN -- its own real, minimal,
// single-view implementation is valid with no nav landmark and no nav
// control at all, `dashboardLabel` degenerating to `primary.navigation_
// label` itself.
const singleDestination = scenario.navigation_destinations.length === 1;
// (8, module docstring): the primary's own real, reconciled `actions` --
// never a route name, never a candidate-specific string -- decide which
// real journey below actually runs.
const primaryIsMutationCapable = (primary.actions || []).some((a) => a === 'create' || a === 'edit');
if (primaryIsMutationCapable && (!primaryBackendId || !/^\d+$/.test(primaryBackendId))) {
  throw new Error('--primary-id must identify the real backend-persisted primary record');
}

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

/** A declared top-level navigation destination's reachability, proved by a
 * real URL transition -- never a heading, an ARIA role beyond link/button,
 * or any domain text (module docstring, gap 6 / STAGED_GENERATION_STAGES.md#8). */
async function navigateTo(page, pattern) {
  const control = await firstVisible([
    page.getByRole('link', { name: pattern }),
    page.getByRole('button', { name: pattern }),
  ]);
  await navigateAndVerifyReachable(page, control);
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
  if (!singleDestination) {
    // (9, module docstring): a real nav landmark is only a real
    // observable when there is a second real destination to have
    // navigated FROM -- a single-destination product renders its one
    // real view directly at `BASE`, already reached above.
    await expect(page.getByRole('navigation')).toBeVisible();
    await navigateTo(page, navPattern(primary.navigation_label));
  }

  if (primaryIsMutationCapable) {
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

    // Gap 7(b), module docstring: prove the edit form genuinely shows this
    // real record's own real data BEFORE any new value is typed over it --
    // never inferred from the post-submit result alone, which a form that
    // was blank all along would satisfy identically.
    for (const fieldName of primary.editable_form_fields) {
      if (!Object.prototype.hasOwnProperty.call(createValues, fieldName)) continue;
      const input = await firstVisible([
        page.getByLabel(fieldPattern(fieldName)), page.getByPlaceholder(fieldPattern(fieldName)),
      ]);
      const currentValue = (await input.inputValue()).trim();
      const expectedValue = String(createValues[fieldName]).trim();
      if (currentValue !== expectedValue) {
        throw new Error(
          `edit form field "${fieldName}" does not show this record's own real value before mutation `
          + `(expected "${expectedValue}", found "${currentValue}") -- the edit form is not genuinely `
          + 'pre-populated'
        );
      }
    }

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
      await navigateTo(page, navPattern(related.navigation_label));
      // Gap 7(a), module docstring: "create" declared in `related.actions`
      // is a real, spec+backend-reconciled promise (`acceptance_plan_
      // compiler.py`'s own `_resolved_actions`) -- a missing control for a
      // declared-mandatory capability is a real FAIL, never a silent skip.
      // SKIP stays legitimate only when neither the candidate's own
      // product_ux_spec.json nor its own real backend routes ever declared
      // "create" for this resource in the first place.
      const relatedMustCreate = (related.actions || []).includes('create');
      const relatedCreate = page.getByRole('link', { name: createButtonPattern(related.singular_label) });
      const relatedCreateCount = await relatedCreate.count();
      if (relatedMustCreate && relatedCreateCount === 0) {
        throw new Error(
          `${related.name} declares a mandatory "create" capability (both product_ux_spec.json and the `
          + 'real backend agree it exists) but no reachable create control was found anywhere on the '
          + `${related.navigation_label} page`
        );
      }
      if (relatedCreateCount) {
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
  }
  // (8, module docstring): a read-only primary's entire observable promise
  // is real navigation -- already proven above by `navigateTo(primary)` --
  // with no console/page/network error; nothing further is asked of it.

  if (!singleDestination) {
    // (9, module docstring): for a single-destination scenario,
    // `dashboardLabel` degenerates to `primary.navigation_label` itself --
    // the page never left it, so a second navigateTo has no real control
    // to click and nothing further to prove.
    await navigateTo(page, navPattern(dashboardLabel));
  }
  if (consoleErrors.length || pageErrors.length || failedRequests.length) {
    throw new Error(JSON.stringify({ consoleErrors, pageErrors, failedRequests }));
  }
  console.log(JSON.stringify({
    outcome: 'BROWSER_JOURNEY_PASS', candidate, mutations,
    validation: primaryIsMutationCapable
      ? 'empty required form emitted no mutation'
      : 'read-only primary: real navigation only, no mutation attempted',
    consoleErrors: 0, pageErrors: 0, failedRequests: 0,
  }));
} finally {
  await browser.close();
}
