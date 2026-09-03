// Real, browser-driven proof that the fix `frontend_form_initial_state_
// preflight.py`'s own findings recommend -- destructure `initialData`,
// seed `useState(initialData || {})`, resync via `useEffect(() =>
// setFormData(initialData || {}), [initialData])` -- genuinely rehydrates
// a form after a real ASYNC update arrives (property D) and never clobbers
// a real user's own typed edits once that has happened (property E).
//
// Real React (the exact react/react-dom UMD bundles `frontend/node_modules`
// already has installed for ARKALI's own product, not a mock or a
// hand-rolled simulation of React's own dependency-array semantics),
// rendered in real Chromium via the same real `@playwright/test`
// `run_golden_browser_journey.mjs`/`run_desktop_journey.mjs` already use.
// No HTTP server needed: `page.setContent()` loads one self-contained HTML
// document (both UMD bundles inlined, real files, byte-for-byte).
//
// Invoked as `node form_initial_state_rehydration.mjs`, exit 0 on every
// assertion passing, non-zero (an uncaught AssertionError) otherwise --
// the same shape `test_golden_browser_journey_capability_coverage.py`'s
// own `_run_journey` subprocess convention already expects.
//
// Run twice, over two structurally unrelated field/entity shapes
// (student name/email, task title/due_date) with the identical component
// source -- proving the fix pattern itself carries no domain-specific
// logic (properties C/H).

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const requireFromFrontend = createRequire(path.join(ROOT, 'frontend', 'package.json'));
const { chromium } = requireFromFrontend('@playwright/test');

const REACT_UMD = readFileSync(
  path.join(ROOT, 'frontend', 'node_modules', 'react', 'umd', 'react.development.js'), 'utf8',
);
const REACT_DOM_UMD = readFileSync(
  path.join(ROOT, 'frontend', 'node_modules', 'react-dom', 'umd', 'react-dom.development.js'), 'utf8',
);

/**
 * The exact fix `frontend_form_initial_state_preflight._form_initial_data_
 * ignored_findings`'s own finding `detail` text recommends, transcribed as
 * real, runnable React -- never a paraphrase. `fields`/`entity` are the
 * only per-domain inputs; the component logic itself never names a field.
 */
function buildAppSource(fields, entity, delayMs) {
  return `
    const { useState, useEffect } = React;

    function Form({ onSubmit, fields, initialData }) {
      const [formData, setFormData] = useState(initialData || {});
      useEffect(() => { setFormData(initialData || {}); }, [initialData]);
      return React.createElement('form', { onSubmit: (e) => { e.preventDefault(); onSubmit(formData); } },
        fields.map((field) => React.createElement('input', {
          key: field, 'data-testid': field, value: formData[field] || '',
          onChange: (e) => {
            const { value } = e.target;
            setFormData((prev) => ({ ...prev, [field]: value }));
          },
        })),
      );
    }

    function Edit() {
      const [entity, setEntity] = useState({});
      const [tick, setTick] = useState(0);
      useEffect(() => {
        const timer = setTimeout(() => setEntity(${JSON.stringify(entity)}), ${delayMs});
        return () => clearTimeout(timer);
      }, []);
      // property E's own trigger: an unrelated parent re-render (a real
      // sibling state change) that never touches "entity" itself.
      window.__triggerUnrelatedRerender = () => setTick((t) => t + 1);
      return React.createElement(Form, { onSubmit: () => {}, fields: ${JSON.stringify(fields)}, initialData: entity });
    }

    ReactDOM.render(React.createElement(Edit), document.getElementById('root'));
  `;
}

function buildHtml(appSource) {
  return `<!doctype html><html><body><div id="root"></div>
    <script>${REACT_UMD}</script>
    <script>${REACT_DOM_UMD}</script>
    <script>${appSource}</script>
  </body></html>`;
}

async function runDomain(browser, { label, fields, entity, delayMs }) {
  const page = await browser.newPage();
  await page.setContent(buildHtml(buildAppSource(fields, entity, delayMs)));

  const [firstField, secondField] = fields;
  const firstInput = page.getByTestId(firstField);

  // Property D: the field starts genuinely empty (the async update has not
  // resolved yet) -- proves this is really testing rehydration-after-mount,
  // not a value that was already correct on first render for free.
  await assert.equal(await firstInput.inputValue(), '', `${label}: expected empty before the async update resolves`);

  // Playwright's own toHaveValue/expect() auto-waits; inputValue() does
  // not, so poll for real -- delayMs plus real margin, never a fixed sleep
  // shorter than the real timer this fixture itself set.
  await page.waitForFunction(
    ([field, expected]) => document.querySelector(`[data-testid="${field}"]`)?.value === expected,
    [firstField, entity[firstField]], { timeout: delayMs + 2000 },
  );
  assert.equal(
    await firstInput.inputValue(), entity[firstField],
    `${label}: property D -- real async update did not rehydrate the form`,
  );

  // Property E: type a real user edit, then force a real, unrelated parent
  // re-render (never touching "entity" itself) -- the typed edit must
  // survive it, proving useEffect's [initialData] dependency array
  // correctly skipped re-running on the unrelated re-render.
  const userEdit = `${entity[firstField]}-edited-by-user`;
  await firstInput.fill(userEdit);
  await page.evaluate(() => window.__triggerUnrelatedRerender());
  await page.waitForTimeout(50);
  assert.equal(
    await firstInput.inputValue(), userEdit,
    `${label}: property E -- an unrelated re-render clobbered the user's own real typed edit`,
  );

  // The second field never touched by the user must still show its own
  // real rehydrated value, unaffected by the first field's own edit.
  if (secondField) {
    assert.equal(
      await page.getByTestId(secondField).inputValue(), entity[secondField],
      `${label}: the second, untouched field lost its own real rehydrated value`,
    );
  }
}

async function main() {
  const browser = await chromium.launch();
  try {
    await runDomain(browser, {
      label: 'student', fields: ['name', 'email'], delayMs: 250,
      entity: { name: 'Ada Lovelace', email: 'ada@example.com' },
    });
    // A second, structurally different domain: different field names, a
    // different real entity shape -- proves buildAppSource's own component
    // logic carries no domain-specific knowledge (properties C/H).
    await runDomain(browser, {
      label: 'task', fields: ['title', 'due_date'], delayMs: 250,
      entity: { title: 'Write report', due_date: '2030-01-01' },
    });
  } finally {
    await browser.close();
  }
  console.log('form_initial_state_rehydration: all assertions passed (properties D, E, C/H)');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
