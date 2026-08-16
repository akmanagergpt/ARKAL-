/**
 * The Command Center shell.
 *
 * Two sections today: the Phase 5 Project Registry slice and the Phase 17
 * Visual Workflow Studio. This is a minimal section switch, not a router —
 * the implementation matrix places a real navigation surface much later, and
 * two `<button>`s over local state is the whole obligation until then. The
 * client is a prop rather than a module-level import so a test can drive the
 * whole application against a controlled transport without the production
 * path gaining a switch it does not need.
 */

import { useState } from 'react';

import type { ArkaliApiClient } from '@/api/client';
import { ProjectRegistryPage } from '@/features/projects/ProjectRegistryPage';
import { WorkflowStudioPage } from '@/features/workflow/WorkflowStudioPage';

type Section = 'projects' | 'workflow';

export function App({ client }: { client: ArkaliApiClient }) {
  const [section, setSection] = useState<Section>('projects');

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
          <nav aria-label="Sections" className="flex gap-2">
            <button
              type="button"
              onClick={() => setSection('projects')}
              aria-current={section === 'projects' ? 'page' : undefined}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                section === 'projects'
                  ? 'bg-slate-900 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              Project Registry
            </button>
            <button
              type="button"
              onClick={() => setSection('workflow')}
              aria-current={section === 'workflow' ? 'page' : undefined}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                section === 'workflow'
                  ? 'bg-slate-900 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              Workflow Studio
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {section === 'projects' ? (
          <ProjectRegistryPage client={client} />
        ) : (
          <WorkflowStudioPage client={client} />
        )}
      </main>
    </div>
  );
}
