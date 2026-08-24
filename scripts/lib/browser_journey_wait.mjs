/**
 * Retry helper shared by the real-browser acceptance journeys
 * (`run_golden_browser_journey.mjs`).
 *
 * A GENERATED CANDIDATE FULL-RELOADS ON EVERY MUTATION. A simple generated
 * CRUD app's own `window.location.href = '/students'` redirect (real, common,
 * unremarkable code - not a defect) means every create/edit/delete
 * legitimately passes through a real browser navigation, a fresh bundle load
 * and a fresh data refetch, during which no nav element exists at all for a
 * real, non-zero window. A single eager visibility check loses that race
 * under real, ordinary load - not hypothetically: reproduced live against
 * golden-work-113's own real build. Retrying is the same tolerance a
 * competent QA engineer's test already grants a real page transition, and
 * mirrors this repository's own `run_desktop_journey.mjs`'s `waitFor` shape
 * exactly. No journey assertion (mutations, console/page errors, failed
 * requests) is weakened by this module - only how long discovery waits
 * before giving up.
 */

export const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

/**
 * The first of `locators` that is visible, retried until one is or `timeout`
 * elapses. `locators` are checked in order on every poll, so an earlier
 * locator that becomes visible always wins over a later one.
 */
export async function firstVisible(locators, timeout = 10_000, wait = delay) {
  const deadline = Date.now() + timeout;
  while (true) {
    for (const locator of locators) {
      if (await locator.count() && await locator.first().isVisible()) return locator.first();
    }
    if (Date.now() >= deadline) break;
    await wait(100);
  }
  throw new Error(`no expected visible control found within ${timeout}ms`);
}

/**
 * Waits until `predicate` matches an entry in the live `mutations` array, or
 * `timeout` elapses.
 *
 * REPLACES A FIXED `waitForTimeout(200)`. That fixed wait was already the
 * only thing standing between a real network mutation and the check that
 * confirms it happened, for every one of this journey's four mutations
 * (create/edit/delete/payment) - and 200ms is not a bound on anything real:
 * a slower first fetch (JIT warmup, host under real load) can exceed it,
 * which is exactly what a live run against golden-work-113's own build did.
 * Polling for the real event, bounded by a generous timeout, is correct
 * where a fixed sleep was always a guess.
 */
export async function waitForMutation(
  mutations, predicate, message, timeout = 5_000, wait = delay,
) {
  const deadline = Date.now() + timeout;
  while (true) {
    if (mutations.some(predicate)) return;
    if (Date.now() >= deadline) break;
    await wait(100);
  }
  throw new Error(message);
}
