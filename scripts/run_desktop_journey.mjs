/** Real Phase 28 Tauri/WebView2 journey. No route interception or fixture. */

import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');
const EXE = process.env.ARKALI_DESKTOP_EXE
  ? path.resolve(process.env.ARKALI_DESKTOP_EXE)
  : path.join(REPO, 'src-tauri', 'target', 'release', 'arkali-desktop.exe');
const requireFromFrontend = createRequire(path.join(REPO, 'frontend', 'package.json'));
const { chromium, expect } = requireFromFrontend('@playwright/test');
const EXISTING_PROJECT_ID = process.env.ARKALI_EXISTING_PROJECT_ID;
const PROJECT_ID = EXISTING_PROJECT_ID ?? `desktop-${Date.now().toString(36)}`;
const PROJECT_NAME = process.env.ARKALI_EXISTING_PROJECT_NAME ?? `Desktop Journey ${PROJECT_ID}`;

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function waitFor(check, label, timeout = 30_000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const result = await check();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await delay(100);
  }
  throw new Error(`${label} timed out${lastError ? `: ${lastError}` : ''}`);
}

async function healthReady() {
  const response = await fetch('http://127.0.0.1:8000/api/health');
  if (!response.ok) return false;
  const body = await response.json();
  return body.status === 'ready' && Object.hasOwn(body, 'schema_revision');
}

async function launch(port) {
  const child = spawn(EXE, [], {
    cwd: REPO,
    env: {
      ...process.env,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${port}`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const output = [];
  child.stdout.on('data', (chunk) => output.push(String(chunk)));
  child.stderr.on('data', (chunk) => output.push(String(chunk)));
  await waitFor(healthReady, 'real backend health');
  const browser = await waitFor(
    async () => chromium.connectOverCDP(`http://127.0.0.1:${port}`),
    'WebView2 CDP endpoint',
  );
  const page = await waitFor(() => {
    for (const context of browser.contexts()) {
      const candidate = context.pages().find((item) => item.url().includes('tauri.localhost'));
      if (candidate) return candidate;
    }
    return false;
  }, 'ARKALI native webview');
  return { child, browser, page, output };
}

async function close(instance) {
  spawnSync(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-Command', `(Get-Process -Id ${instance.child.pid}).CloseMainWindow()`],
    { stdio: 'ignore' },
  );
  await waitFor(() => instance.child.exitCode !== null, 'native window clean shutdown', 10_000);
  await instance.browser.close().catch(() => {});
  await waitFor(async () => {
    try { return !(await healthReady()); } catch { return true; }
  }, 'owned backend shutdown', 10_000);
  if (instance.child.exitCode !== 0) {
    throw new Error(`desktop exited ${instance.child.exitCode}: ${instance.output.join('')}`);
  }
}

async function openExpertProjects(page) {
  await page.getByRole('button', { name: 'Uzman', exact: true }).click();
  await page.getByRole('button', { name: 'Yönetilen Ürünler', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Projeler' })).toBeVisible();
}

let first;
let second;
try {
  first = await launch(9331);
  const consoleErrors = [];
  first.page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  await expect(first.page.getByText('ARKALI', { exact: true })).toBeVisible();
  await expect(first.page.getByRole('button', { name: 'Başlangıç' })).toHaveAttribute('aria-pressed', 'true');
  await first.page.getByRole('button', { name: 'Profesyonel', exact: true }).click();
  await expect(first.page.getByRole('button', { name: 'Profesyonel' })).toHaveAttribute('aria-pressed', 'true');
  await openExpertProjects(first.page);
  if (!EXISTING_PROJECT_ID) {
    await first.page.getByLabel(/proje tanımlayıcısı/i).fill(PROJECT_ID);
    await first.page.getByLabel(/proje adı/i).fill(PROJECT_NAME);
    await first.page.getByRole('button', { name: /projeyi kaydet/i }).click();
    await expect(first.page.getByText(/kaydedildi \(DRAFT\)/i)).toBeVisible();
  }

  const duplicate = spawn(EXE, [], { cwd: REPO, stdio: 'ignore' });
  await waitFor(() => duplicate.exitCode !== null, 'duplicate instance refusal', 10_000);
  if (duplicate.exitCode !== 0) throw new Error(`duplicate instance exited ${duplicate.exitCode}`);
  await expect(first.page.getByRole('button', { name: new RegExp(PROJECT_NAME) })).toBeVisible();

  await first.page.getByRole('button', { name: 'Workflow Studio', exact: true }).click();
  await expect(first.page.getByText('Visual Workflow Studio')).toBeVisible();
  if (consoleErrors.length) throw new Error(`desktop console errors: ${consoleErrors.join(' | ')}`);
  await close(first);
  first = undefined;

  second = await launch(9332);
  await openExpertProjects(second.page);
  await expect(second.page.getByRole('button', { name: new RegExp(PROJECT_NAME) })).toBeVisible();
  await second.page.reload();
  await expect(second.page.getByRole('button', { name: 'Başlangıç' })).toHaveAttribute('aria-pressed', 'true');
  await close(second);
  second = undefined;

  console.log(JSON.stringify({
    result: 'PASS',
    executable: EXE,
    projectId: PROJECT_ID,
    projectOperation: EXISTING_PROJECT_ID ? 'preserved existing project' : 'created project',
    backend: 'real FastAPI + Alembic + SQLite app-data',
    nativeWindow: true,
    modes: ['BEGINNER', 'PROFESSIONAL', 'EXPERT'],
    projectRegistry: 'create + restart persistence',
    workflowStudio: 'rendered in EXPERT',
    duplicateInstance: 'focused existing instance; second process exited',
    cleanShutdown: 'window close + backend unavailable',
    consoleErrors: 0,
  }, null, 2));
} finally {
  if (first) await close(first).catch(() => first.child.kill());
  if (second) await close(second).catch(() => second.child.kill());
}
