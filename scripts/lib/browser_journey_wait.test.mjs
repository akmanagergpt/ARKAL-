/**
 * Regression coverage for the golden-work-113 real-browser acceptance
 * failure: `firstVisible` lost a real race against a generated candidate's
 * own full-page reload on mutation (`no expected visible control found`,
 * reproduced live). These tests use fake locators (Playwright is not a
 * dependency here) to prove the retry/timeout contract directly, with no
 * real browser or timers required.
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { firstVisible, navigateAndVerifyReachable, pathnameOf } from './browser_journey_wait.mjs';

function fakeLocator({ count, visible }) {
  const resolved = { isVisible: async () => visible };
  return {
    count: async () => count,
    first: () => resolved,
  };
}

/** A synchronous stand-in for `delay` so the retry loop needs no real time. */
function instantWait() {
  return Promise.resolve();
}

test('returns the first locator that is already visible', async () => {
  const wanted = fakeLocator({ count: 1, visible: true });
  const result = await firstVisible([wanted], 1000, instantWait);
  assert.equal(await result.isVisible(), true);
});

test('prefers an earlier locator over a later one that is also visible', async () => {
  const earlier = fakeLocator({ count: 1, visible: true });
  const later = fakeLocator({ count: 1, visible: true });
  const result = await firstVisible([earlier, later], 1000, instantWait);
  assert.equal(result, earlier.first());
  assert.notEqual(result, later.first());
});

test('retries until a transiently-absent control becomes visible', async () => {
  let calls = 0;
  const flaky = {
    count: async () => {
      calls += 1;
      return calls >= 3 ? 1 : 0;
    },
    first: () => ({ isVisible: async () => true }),
  };
  const result = await firstVisible([flaky], 1000, instantWait);
  assert.equal(await result.isVisible(), true);
  assert.ok(calls >= 3, 'expected at least 3 polls before the control appeared');
});

test('falls back to a later locator once the earlier one is visible', async () => {
  let earlierCalls = 0;
  const earlier = {
    count: async () => {
      earlierCalls += 1;
      return 0;
    },
    first: () => ({ isVisible: async () => true }),
  };
  const later = fakeLocator({ count: 1, visible: true });
  const result = await firstVisible([earlier, later], 1000, instantWait);
  assert.equal(result, later.first());
  assert.ok(earlierCalls >= 1);
});

test('throws with a labelled error once the timeout elapses', async () => {
  const neverVisible = fakeLocator({ count: 0, visible: false });
  let clock = 0;
  const controlledWait = () => {
    clock += 100;
    return Promise.resolve();
  };
  const originalNow = Date.now;
  let elapsed = 0;
  Date.now = () => elapsed;
  const advancingWait = async () => {
    elapsed += 100;
    await controlledWait();
  };
  try {
    await assert.rejects(
      () => firstVisible([neverVisible], 500, advancingWait),
      /no expected visible control found within 500ms/,
    );
  } finally {
    Date.now = originalNow;
  }
});

test('pathnameOf normalizes a relative href and an absolute URL to the same path', () => {
  assert.equal(pathnameOf('/payments'), '/payments');
  assert.equal(pathnameOf('http://127.0.0.1:3000/payments'), '/payments');
  assert.equal(pathnameOf('/payments/'), '/payments');
  assert.equal(pathnameOf('/'), '/');
});

/** A fake page: `url()` reports whatever `navigateTo` last set, exactly the
 * synchronous `Page.url()` shape `navigateAndVerifyReachable` relies on. */
function fakePage(initialUrl) {
  let current = initialUrl;
  return {
    url: () => current,
    navigateTo(next) { current = next; },
  };
}

function fakeControl({ href = null, onClick } = {}) {
  return {
    getAttribute: async (name) => (name === 'href' ? href : null),
    click: async () => { if (onClick) await onClick(); },
  };
}

test(
  'a real link control is proved reachable once the URL matches its own declared href '
  + '(golden-work-128 case A: a valid routable page with no heading passes)',
  async () => {
    const page = fakePage('http://127.0.0.1:3000/');
    const control = fakeControl({
      href: '/payments',
      onClick: () => page.navigateTo('http://127.0.0.1:3000/payments'),
    });
    // Must not throw -- no heading, no page content, no domain text is
    // inspected anywhere in this call.
    await navigateAndVerifyReachable(page, control, 1000, instantWait);
  },
);

test(
  'a real link control is refused when the URL never transitions to its own declared href '
  + '(case B: a declared destination that is genuinely unreachable fails)',
  async () => {
    const page = fakePage('http://127.0.0.1:3000/');
    const control = fakeControl({ href: '/payments' }); // click does nothing
    await assert.rejects(
      () => navigateAndVerifyReachable(page, control, 500, instantWait),
      /never navigated to a URL matching that path/,
    );
  },
);

test('a control with no href (a button-driven route push) is proved reachable by a real URL change', async () => {
  const page = fakePage('http://127.0.0.1:3000/students');
  const control = fakeControl({
    href: null,
    onClick: () => page.navigateTo('http://127.0.0.1:3000/dashboard'),
  });
  await navigateAndVerifyReachable(page, control, 1000, instantWait);
});

test('a control with no href that produces no real navigation is refused', async () => {
  const page = fakePage('http://127.0.0.1:3000/students');
  const control = fakeControl({ href: null }); // click does nothing
  await assert.rejects(
    () => navigateAndVerifyReachable(page, control, 500, instantWait),
    /produced no real navigation/,
  );
});
