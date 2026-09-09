/**
 * The Tanılama page (Command Center Wave 2C, Surface C).
 *
 * READ-ONLY, REPRESENTATION ONLY. Renders `GET /api/diagnostics/snapshot`
 * and nothing else — no finding, job or architecture truth is decided here,
 * only shown. `operational_hint` is a structured value the backend derives
 * fresh from live state on every call (never free text, never stale) —
 * mapped below to one plain Turkish sentence per value, the whole answer to
 * "what should I do next", never a raw enum shown to Beginner.
 */

import type { SkillMode } from '@/app/SkillModeSwitch';
import type { ArkaliApiClient } from '@/api/client';
import type { _DiagnosticsFinding } from '@/api/contracts';
import { Button, Callout, PageHeader, Panel, Spinner } from '@/components/ui';

import { useDiagnosticsSnapshot } from './useDiagnosticsSnapshot';

const NEXT_STEP_TEXT: Record<string, string> = {
  resolve_open_finding: 'Önce açık kritik sorunları çözün.',
  review_pending_product_change: 'Bekleyen bir değişiklik incelemesi var.',
  pending_operational_job: 'Şu anda çalışan bir işlem var, bitmesini bekleyin.',
  no_pending_operational_work: 'Şu anda yapmanız gereken bir işlem yok.',
  live_state_unavailable: 'Çalışma durumu şu anda okunamadı.',
};

function nextStepText(hint: string): string {
  return NEXT_STEP_TEXT[hint] ?? 'Durum bilinmiyor.';
}

function Header({ onRefresh, refreshing = false }: { onRefresh?: () => void; refreshing?: boolean }) {
  return (
    <PageHeader
      title="Tanılama"
      subtitle="Sistem durumu, açık sorunlar ve mimari durum doğrudan ARKALI'nin canlı kayıtlarından okunur; burada hiçbir değer yeniden üretilmez."
      actions={onRefresh === undefined ? undefined : (
        <Button onClick={onRefresh} busy={refreshing}>Yenile</Button>
      )}
    />
  );
}

function FindingRow({ finding }: { finding: _DiagnosticsFinding }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-900">{finding.identifier}</p>
        {finding.detail ? <p className="mt-0.5 truncate text-xs text-slate-500">{finding.detail}</p> : null}
      </div>
      <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-inset ring-amber-600/20">
        {finding.severity}
      </span>
    </div>
  );
}

export function DiagnosticsPage({ client, mode }: { client: ArkaliApiClient; mode: SkillMode }) {
  const state = useDiagnosticsSnapshot(client);

  if (state.loading) {
    return (
      <div className="flex flex-col gap-6">
        <Header />
        <div className="flex items-center justify-center rounded-xl border border-slate-200 bg-white py-16">
          <Spinner label="Sistem durumu okunuyor…" />
        </div>
      </div>
    );
  }

  if (state.snapshot === null) {
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <Callout tone="error" title="Sistem durumu okunamadı">
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
  const healthy = snapshot.overall_status === 'HEALTHY';

  if (mode === 'beginner') {
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <Callout tone={healthy ? 'success' : 'muted'} title={healthy ? 'Sistem sağlıklı' : 'Dikkat edilmesi gereken sorunlar var'}>
          <p>
            Açık kritik sorun: <strong>{snapshot.open_stopping_count}</strong> · Mimari durum:{' '}
            <strong>{snapshot.architecture.gates_passed}/{snapshot.architecture.gates_total}</strong>
          </p>
        </Callout>
        <Panel title="Sonraki önerilen işlem">
          <p className="py-1 text-sm text-slate-700">{nextStepText(snapshot.operational_hint)}</p>
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Header onRefresh={state.reload} refreshing={state.refreshing} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Genel durum">
          <div className="flex flex-col gap-2 py-1 text-sm">
            <p className="text-slate-700">Durum: <strong>{snapshot.overall_status}</strong></p>
            <p className="text-slate-700">Açık kritik sorun: <strong>{snapshot.open_stopping_count}</strong></p>
            <p className="text-slate-700">
              Mimari durum: <strong>{snapshot.architecture.gates_passed}/{snapshot.architecture.gates_total}</strong> kontrol geçti
            </p>
            <p className="text-slate-700">Sonraki işlem: {nextStepText(snapshot.operational_hint)}</p>
          </div>
        </Panel>
        <Panel title="Açık bulgular">
          {snapshot.top_findings.length === 0 ? (
            <p className="py-1 text-sm text-slate-500">Açık bulgu yok.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {snapshot.top_findings.map((finding) => (
                <FindingRow key={finding.identifier} finding={finding} />
              ))}
            </div>
          )}
        </Panel>
      </div>
      {mode === 'expert' && snapshot.architecture.violations.length > 0 ? (
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
