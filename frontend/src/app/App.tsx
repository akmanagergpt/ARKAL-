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
import { FactoryHistoryPage } from '@/features/factory/FactoryHistoryPage';
import { OperationsPage } from '@/features/operations/OperationsPage';
import { ProjectRegistryPage } from '@/features/projects/ProjectRegistryPage';
import { WorkflowStudioPage } from '@/features/workflow/WorkflowStudioPage';
import { COMMAND_AREAS, type AreaId } from './areas';
import { CommandCenterHome } from './CommandCenterHome';
import { SkillModeSwitch, type SkillMode } from './SkillModeSwitch';

export function App({ client }: { client: ArkaliApiClient }) {
  const [area, setArea] = useState<AreaId>('command');
  const [mode, setMode] = useState<SkillMode>('beginner');

  function changeMode(next: SkillMode) {
    setMode(next);
    if (area === 'workflow' && next !== 'expert') setArea('command');
  }

  const content = area === 'products'
    ? <ProjectRegistryPage client={client} showTechnical={mode === 'expert'} />
    : area === 'workflow'
      ? <WorkflowStudioPage client={client} />
      : area === 'operations'
        ? <OperationsPage client={client} />
        : area === 'factory'
          ? <FactoryHistoryPage client={client} />
          : <CommandCenterHome navigate={setArea} mode={mode} />;

  return (
    <div className="min-h-full bg-slate-50 lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="border-b border-slate-200 bg-white lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between px-5 py-5 lg:block">
          <button type="button" onClick={() => setArea('command')} className="text-left"><span className="block text-lg font-bold tracking-tight text-slate-950">ARKALI</span><span className="block text-xs font-medium text-slate-500">Command Center</span></button>
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">Yerel</span>
        </div>
        <nav aria-label="Ana alanlar" className="flex gap-1 overflow-x-auto px-3 pb-4 lg:block lg:space-y-1 lg:overflow-visible">
          {COMMAND_AREAS.map((item) => { const available = item.available && (item.id !== 'workflow' || mode === 'expert'); return <button key={item.id} type="button" disabled={!available} aria-current={area === item.id ? 'page' : undefined} title={!available ? `${item.label} bu düzeyde kullanılamıyor` : item.description} onClick={() => setArea(item.id)} className={`group min-w-max rounded-lg px-3 py-2 text-left text-sm transition lg:block lg:w-full ${area === item.id ? 'bg-slate-950 font-semibold text-white' : available ? 'text-slate-700 hover:bg-slate-100 hover:text-slate-950' : 'cursor-not-allowed text-slate-400'}`}><span>{item.label}</span>{!item.available ? <span className="ml-2 text-[10px] uppercase tracking-wide">Yakında</span> : item.id === 'workflow' && mode !== 'expert' ? <span className="ml-2 text-[10px] uppercase tracking-wide">Uzman</span> : null}</button>; })}
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur sm:px-6 lg:px-8"><p className="text-sm font-medium text-slate-600">{COMMAND_AREAS.find((item) => item.id === area)?.description}</p><SkillModeSwitch mode={mode} onChange={changeMode} /></header>
        <main className="mx-auto max-w-7xl px-4 py-7 sm:px-6 lg:px-8">{content}</main>
      </div>
    </div>
  );
}
