/**
 * The Kod Zekâsı page (Command Center Wave 2B, Surface B).
 *
 * READ-ONLY. Renders `GET /api/code-intelligence/snapshot` and nothing else.
 * Every figure is real and re-derived on each call from
 * `engineering.codeintel`'s own import graph plus the real architecture
 * gate — never a raw graph, never an internal class name (`PythonGraphBuilder`
 * stays a backend implementation detail), never an absolute path.
 *
 * BEGINNER gets plain Turkish answers to the four questions this wave
 * scoped: file count, structural health, and the internal areas most other
 * code depends on (doubling as "what a change there could affect").
 * Professional adds the bounded per-area breakdown and a violation count;
 * Expert adds the real violation detail strings, matching this surface's
 * own `ArchitectureSummary.violations` field one for one — never inventing
 * a fourth tier of data that does not exist.
 */

import type { SkillMode } from '@/app/SkillModeSwitch';
import type { ArkaliApiClient } from '@/api/client';
import type { _CodeIntelligenceDependencyArea } from '@/api/contracts';
import { Button, Callout, PageHeader, Panel, Spinner } from '@/components/ui';

import { useCodeIntelligenceSnapshot } from './useCodeIntelligenceSnapshot';

function Header({ onRefresh, refreshing = false }: { onRefresh?: () => void; refreshing?: boolean }) {
  return (
    <PageHeader
      title="Kod Zekâsı"
      subtitle="Kod yapısı, bağımlılıklar ve mimari durum doğrudan ARKALI'nin canlı analizinden okunur; burada hiçbir değer yeniden üretilmez."
      actions={onRefresh === undefined ? undefined : (
        <Button onClick={onRefresh} busy={refreshing}>Yenile</Button>
      )}
    />
  );
}

function areaNames(areas: _CodeIntelligenceDependencyArea[], count: number): string {
  return areas.slice(0, count).map((a) => a.area).join(', ');
}

export function CodeIntelligencePage({ client, mode }: { client: ArkaliApiClient; mode: SkillMode }) {
  const state = useCodeIntelligenceSnapshot(client);

  if (state.loading) {
    return (
      <div className="flex flex-col gap-6">
        <Header />
        <div className="flex items-center justify-center rounded-xl border border-slate-200 bg-white py-16">
          <Spinner label="Kod yapısı analiz ediliyor…" />
        </div>
      </div>
    );
  }

  if (state.snapshot === null) {
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <Callout tone="error" title="Kod yapısı okunamadı">
          <p>{state.failure?.message ?? 'Bilinmeyen bir hata oluştu.'}</p>
          <div className="mt-3">
            <Button onClick={state.reload} busy={state.refreshing} variant="primary">
              Yeniden dene
            </Button>
          </div>
        </Callout>
      </div>
    );
  }

  const snapshot = state.snapshot;
  const healthy = snapshot.architecture.gates_passed === snapshot.architecture.gates_total;
  const violationCount = snapshot.architecture.violations.length;

  if (mode === 'beginner') {
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <Panel title="Proje yapısı">
          <p className="text-sm text-slate-700">
            Projede <strong>{snapshot.module_count}</strong> ana dosya var.
          </p>
        </Panel>
        <Callout tone={healthy ? 'success' : 'muted'} title={healthy ? 'Yapı sağlıklı görünüyor.' : `Yapıda ${violationCount} alanda sorun var.`}>
          {snapshot.top_dependencies.length > 0 ? (
            <p>
              Bir değişiklik en çok şu alanları etkileyebilir: {areaNames(snapshot.top_dependencies, 3)}.
            </p>
          ) : null}
        </Callout>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Header onRefresh={state.reload} refreshing={state.refreshing} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Genel bakış">
          <div className="flex flex-col gap-2 py-1 text-sm">
            <p className="text-slate-700">Ana dosya sayısı: <strong>{snapshot.module_count}</strong></p>
            <p className="text-slate-700">
              Mimari durum: <strong>{snapshot.architecture.gates_passed}/{snapshot.architecture.gates_total}</strong> kontrol geçti
              {violationCount > 0 ? ` (${violationCount} sorun)` : ''}
            </p>
          </div>
        </Panel>
        <Panel title="En çok bağlantılı alanlar">
          <div className="divide-y divide-slate-100">
            {snapshot.top_dependencies.map((dep) => (
              <div key={dep.area} className="flex items-center justify-between gap-3 py-2">
                <span className="text-sm font-medium text-slate-900">{dep.area}</span>
                <span className="font-mono text-sm text-slate-600">{dep.dependent_count}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      {mode === 'expert' && violationCount > 0 ? (
        <Panel title="Mimari bulgular">
          <ul className="flex flex-col gap-2 py-1 text-sm text-slate-700">
            {snapshot.architecture.violations.map((violation) => (
              <li key={violation} className="break-words font-mono text-xs">{violation}</li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
