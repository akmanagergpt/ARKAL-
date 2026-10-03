import { useMemo, useState } from 'react';

import type { ArkaliApiClient } from '@/api/client';
import { FactoryHistoryPage } from '@/features/factory/FactoryHistoryPage';
import { OperationsPage } from '@/features/operations/OperationsPage';
import { ProjectRegistryPage } from '@/features/projects/ProjectRegistryPage';
import { ProvidersPage } from '@/features/providers/ProvidersPage';
import { CodeIntelligencePage } from '@/features/codeintel/CodeIntelligencePage';
import { DiagnosticsPage } from '@/features/diagnostics/DiagnosticsPage';
import { WorkflowStudioPage } from '@/features/workflow/WorkflowStudioPage';
import { COMMAND_AREAS, type AreaId } from './areas';
import { CommandCenterHome } from './CommandCenterHome';
import { SkillModeSwitch, type SkillMode } from './SkillModeSwitch';

const ICONS: Record<string, string> = {
  command: 'M4 6h16M4 12h16M4 18h16',
  factory: 'M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6',
  products: 'M4 7h16v13H4zM8 7V4h8v3',
  workflow: 'M6 4v16M18 4v16M6 12h12',
  team: 'M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M20 8v6M23 11h-6',
  providers: 'M12 2v20M2 12h20M5 5l14 14M19 5 5 19',
  operations: 'M4 19V9M10 19V5M16 19v-7M22 19V3',
  knowledge: 'M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21z',
  'code-intelligence': 'M8 9l-3 3 3 3M16 9l3 3-3 3M14 5l-4 14',
  evolution: 'M20 11a8 8 0 1 1-2.3-5.7M20 4v7h-7',
  extensions: 'M20 13v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6M15 3h6v6M21 3l-9 9',
  security: 'M12 3l8 4v5c0 5-3.4 8.2-8 9-4.6-.8-8-4-8-9V7z',
  release: 'M12 3v13M7 11l5 5 5-5M5 21h14',
  diagnostics: 'M10.3 3.5h3.4l.8 2.2 2.1.9 2.1-1.1 2.4 2.4-1.1 2.1.9.8 2.2-1.7 1.6.2 2.4-2.1 1.1-.9 2.1 1.1 2.1-2.4 1.1-1.6-.2-2.2 1.7-.8-2.2-2.1-.9-2.1 1.1-2.4-2.4 1.1-2.1-.9-.8-2.2 1.7-1.6-.2-2.4 2.1-1.1.9-2.1-1.1-2.1 2.4-1.1 1.6.2zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
};

function Icon({ id, size = 18 }: { id: string; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={ICONS[id] ?? ICONS.command} /></svg>;
}

export function App({ client }: { client: ArkaliApiClient }) {
  const [area, setArea] = useState<AreaId>('command');
  const [mode, setMode] = useState<SkillMode>('beginner');
  const [rightPanel, setRightPanel] = useState<'context' | 'files' | 'changes' | 'terminal' | 'tasks' | 'memory' | 'agents'>('context');
  const [sidebarOpen, setSidebarOpen] = useState(true);

  function changeMode(next: SkillMode) {
    setMode(next);
    if (area === 'workflow' && next !== 'expert') setArea('command');
  }

  const current = useMemo(() => COMMAND_AREAS.find((item) => item.id === area)!, [area]);

  const content = area === 'products'
    ? <ProjectRegistryPage client={client} showTechnical={mode === 'expert'} />
    : area === 'workflow'
      ? <WorkflowStudioPage client={client} />
      : area === 'operations'
        ? <OperationsPage client={client} />
        : area === 'providers'
          ? <ProvidersPage client={client} mode={mode} />
          : area === 'code-intelligence'
            ? <CodeIntelligencePage client={client} mode={mode} />
            : area === 'diagnostics'
              ? <DiagnosticsPage client={client} mode={mode} />
              : area === 'factory'
                ? <FactoryHistoryPage client={client} showTechnical={mode === 'expert'} />
                : <CommandCenterHome navigate={setArea} mode={mode} client={client} />;

  const visibleAreas = COMMAND_AREAS.filter((item) => item.available || ['command', 'factory', 'products', 'providers', 'operations', 'code-intelligence', 'diagnostics'].includes(item.id));

  return (
    <div className="arkali-shell">
      <aside className={`arkali-sidebar ${sidebarOpen ? 'is-open' : 'is-collapsed'}`}>
        <div className="arkali-brand">
          <button type="button" className="arkali-brand-mark" onClick={() => setArea('command')} aria-label="ARKALI Ana Sayfa">A</button>
          {sidebarOpen ? <div className="min-w-0"><div className="arkali-brand-name">ARKALI</div><div className="arkali-brand-sub">AI Desktop OS</div></div> : null}
          {sidebarOpen ? <button type="button" className="arkali-icon-button" onClick={() => setSidebarOpen(false)} aria-label="Menüyü daralt">‹</button> : null}
        </div>

        <div className="arkali-local-status"><span className="arkali-status-dot" />{sidebarOpen ? <><strong>Yerel çalışma alanı</strong><span>Bağlı</span></> : null}</div>

        <nav className="arkali-nav" aria-label="ARKALI alanları">
          <div className="arkali-nav-label">{sidebarOpen ? 'ÇALIŞMA ALANI' : '•'}</div>
          {visibleAreas.map((item) => {
            const available = item.available && (item.id !== 'workflow' || mode === 'expert');
            return <button key={item.id} type="button" disabled={!available} aria-current={area === item.id ? 'page' : undefined} title={!available ? `${item.label} bu düzeyde kullanılamıyor` : item.description} onClick={() => setArea(item.id)} className={`arkali-nav-item ${area === item.id ? 'active' : ''} ${!available ? 'disabled' : ''}`}><Icon id={item.id} />{sidebarOpen ? <span>{item.label}</span> : null}{sidebarOpen && !item.available ? <em>Yakında</em> : null}</button>;
          })}
        </nav>

        <div className="arkali-sidebar-footer">
          <button type="button" className="arkali-nav-item" onClick={() => setArea('diagnostics')}><Icon id="diagnostics" />{sidebarOpen ? <span>Tanılama</span> : null}</button>
          {sidebarOpen ? <div className="arkali-build">LOCAL-FIRST · DESKTOP</div> : null}
        </div>
      </aside>

      <section className="arkali-main">
        <header className="arkali-topbar">
          <div className="flex items-center gap-2 min-w-0">
            {!sidebarOpen ? <button type="button" className="arkali-icon-button" onClick={() => setSidebarOpen(true)} aria-label="Menüyü aç">☰</button> : null}
            <div className="min-w-0"><div className="arkali-breadcrumb">ARKALI <span>/</span> {current.label}</div><div className="arkali-page-description">{current.description}</div></div>
          </div>
          <div className="flex items-center gap-2">
            <div className="arkali-runtime-pill"><span className="arkali-status-dot" /> Qwen / Yerel</div>
            <SkillModeSwitch mode={mode} onChange={changeMode} />
          </div>
        </header>

        <div className="arkali-workspace">
          <main className="arkali-content">{content}</main>

          <aside className="arkali-intelligence">
            <div className="arkali-intelligence-head"><div><div className="arkali-panel-kicker">INTELLIGENCE</div><h2>Çalışma Paneli</h2></div><span className="arkali-live-chip">LIVE</span></div>
            <div className="arkali-right-tabs">
              {(['context','files','changes','terminal','tasks','memory','agents'] as const).map((tab) => <button key={tab} type="button" className={rightPanel === tab ? 'active' : ''} onClick={() => setRightPanel(tab)}>{({context:'Bağlam',files:'Dosyalar',changes:'Değişiklikler',terminal:'Terminal',tasks:'Görevler',memory:'Hafıza',agents:'Ajanlar'} as Record<string,string>)[tab]}</button>)}
            </div>
            <div className="arkali-right-body">
              {rightPanel === 'context' ? <><div className="arkali-context-card"><span className="arkali-context-icon">⌁</span><div><strong>Aktif oturum</strong><p>ARKALI çalışma alanı hazır.</p></div></div><div className="arkali-mini-list"><div><span>Mod</span><b>{mode === 'expert' ? 'Uzman' : mode === 'professional' ? 'Profesyonel' : 'Başlangıç'}</b></div><div><span>Alan</span><b>{current.label}</b></div><div><span>Runtime</span><b>Yerel</b></div><div><span>Backend</span><b>Hazır</b></div></div></> : null}
              {rightPanel === 'files' ? <div className="arkali-empty-state"><Icon id="products" size={24} /><strong>Dosya çalışma alanı</strong><p>Aktif üretim veya proje seçildiğinde gerçek dosya bağlamı burada gösterilecek.</p></div> : null}
              {rightPanel === 'changes' ? <div className="arkali-empty-state"><Icon id="code-intelligence" size={24} /><strong>Değişiklikler</strong><p>Üretim veya değişiklik işi çalıştığında gerçek diff ve kabul akışı burada görünecek.</p></div> : null}
              {rightPanel === 'terminal' ? <div className="arkali-terminal"><div><span>●</span> ARKALI terminal</div><pre>Yerel çalışma alanı hazır.{`\n`}$ _</pre></div> : null}
              {rightPanel === 'tasks' ? <div className="arkali-empty-state"><Icon id="operations" size={24} /><strong>Görevler</strong><p>Gerçek durable işler ve checkpoint'ler burada izlenecek.</p></div> : null}
              {rightPanel === 'memory' ? <div className="arkali-empty-state"><Icon id="knowledge" size={24} /><strong>Proje hafızası</strong><p>Kalıcı bağlam ve karar kayıtları burada tutulacak.</p></div> : null}
              {rightPanel === 'agents' ? <div className="arkali-empty-state"><Icon id="team" size={24} /><strong>AI ajanları</strong><p>Ajan çalışma alanı sonraki canlı orchestrator aşamasına bağlıdır.</p></div> : null}
            </div>
            <div className="arkali-right-footer"><span>Güvenli yerel oturum</span><span>●</span></div>
          </aside>
        </div>
      </section>
    </div>
  );
}
