/**
 * T10 browser/E2E configuration.
 *
 * VERIFICATION_ARCHITECTURE.md 1.1 puts T10 at execution level L2 with **no**
 * mocks: a real browser, a real frontend build, a real backend process and a
 * real database. All four are started here.
 *
 * - the API is the real `surfaces.command` application bound to a real socket
 *   by `scripts/run_command_center.py` over a real Alembic-migrated SQLite file;
 * - the frontend is `vite preview`, which serves the **production build**, so
 *   the journey exercises the artifact that would ship rather than a dev server;
 * - requests reach the API through the Vite proxy, so the browser stays on one
 *   origin and no CORS relaxation exists anywhere.
 *
 * The launcher is given `--fresh`, so it deletes the database before migrating
 * it. The reset lives in the process that owns the file handle rather than in
 * a setup hook, because Playwright starts `webServer` first and the hook would
 * be trying to unlink a database the API had already opened.
 */

import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const API_PORT = 8391;
const WEB_PORT = 4391;
// The package is an ES module, so `__dirname` does not exist.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..');

export const E2E_DATABASE = path.resolve(HERE, 'test-results/e2e/command_center.db');
export const BASE_URL = `http://127.0.0.1:${WEB_PORT}`;

export default defineConfig({
  testDir: './tests/e2e',
  // The journey is a sequence: what is created in one step must still be there
  // in the next. Running it in parallel would prove nothing about persistence.
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  reporter: [['list']],
  timeout: 60_000,
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command:
        `python scripts/run_command_center.py --fresh --port ${API_PORT} --db "${E2E_DATABASE}"`,
      cwd: REPO_ROOT,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 120_000,
    },
    {
      command: `npx vite build && npx vite preview --port ${WEB_PORT} --strictPort`,
      cwd: HERE,
      url: BASE_URL,
      reuseExistingServer: false,
      env: { ARKALI_API_TARGET: `http://127.0.0.1:${API_PORT}` },
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 180_000,
    },
  ],
});
