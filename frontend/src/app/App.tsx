/**
 * The Command Center shell.
 *
 * One page today, by design: this is the first vertical slice, not the
 * consolidated Command Center, which the implementation matrix places much
 * later. The client is a prop rather than a module-level import so a test can
 * drive the whole application against a controlled transport without the
 * production path gaining a switch it does not need.
 */

import type { ArkaliApiClient } from '@/api/client';
import { ProjectRegistryPage } from '@/features/projects/ProjectRegistryPage';

export function App({ client }: { client: ArkaliApiClient }) {
  return (
    <div className="min-h-full bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-4 sm:px-6">
          <div className="flex items-baseline gap-3">
            <span className="text-base font-semibold tracking-tight text-slate-900">
              ARKALI
            </span>
            <span className="text-sm text-slate-500">Command Center</span>
          </div>
          <nav aria-label="Sections">
            <span className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
              Project Registry
            </span>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <ProjectRegistryPage client={client} />
      </main>
    </div>
  );
}
