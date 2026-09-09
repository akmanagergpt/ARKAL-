/**
 * The Sağlayıcılar ve Modeller page (Command Center Wave 2, Surface A).
 *
 * READ-ONLY. Renders `GET /api/providers/snapshot` and nothing else — no
 * provider mutation or settings change exists here; this wave authorized
 * read-only productization only. Every dimension is shown exactly as
 * `DimensionReading.state` reports it, the identical honest-reporting rule
 * `DimensionRow`/Operations already established — nothing is invented to
 * fill in an absent local model.
 *
 * BEGINNER GETS ONE PLAIN-LANGUAGE LINE, NEVER BACKEND JARGON. Professional
 * and Expert both get the full per-dimension breakdown — there is no deeper
 * "raw evidence" behind this surface than what `DimensionReading.detail`
 * already carries, so inventing a third tier here would be decoration, not
 * information.
 */

import type { SkillMode } from '@/app/SkillModeSwitch';
import type { ArkaliApiClient } from '@/api/client';
import type { DimensionReading, _ProvidersSnapshotResponse } from '@/api/contracts';
import { Button, Callout, PageHeader, Panel, Spinner } from '@/components/ui';

import { DimensionRow } from '../operations/DimensionRow';
import { useProvidersSnapshot } from './useProvidersSnapshot';

function readings(snapshot: _ProvidersSnapshotResponse): DimensionReading[] {
  return [snapshot.local_runtime, snapshot.configured_model, snapshot.accelerator];
}

function beginnerSummary(
  snapshot: _ProvidersSnapshotResponse,
): { ready: boolean; text: string } {
  if (snapshot.local_runtime.state === 'PASS') {
    return { ready: true, text: 'Yerel AI hazır.' };
  }
  return { ready: false, text: 'Yerel AI şu anda kullanılamıyor.' };
}

function Header({ onRefresh, refreshing = false }: { onRefresh?: () => void; refreshing?: boolean }) {
  return (
    <PageHeader
      title="Sağlayıcılar ve Modeller"
      subtitle="Yerel AI çalışma zamanının durumu doğrudan ARKALI'nin canlı probundan okunur; burada hiçbir değer yeniden üretilmez."
      actions={onRefresh === undefined ? undefined : (
        <Button onClick={onRefresh} busy={refreshing}>Yenile</Button>
      )}
    />
  );
}

export function ProvidersPage({ client, mode }: { client: ArkaliApiClient; mode: SkillMode }) {
  const state = useProvidersSnapshot(client);

  if (state.loading) {
    return (
      <div className="flex flex-col gap-6">
        <Header />
        <div className="flex items-center justify-center rounded-xl border border-slate-200 bg-white py-16">
          <Spinner label="Sağlayıcı durumu yükleniyor…" />
        </div>
      </div>
    );
  }

  if (state.snapshot === null) {
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <Callout tone="error" title="Sağlayıcı durumu okunamadı">
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

  if (mode === 'beginner') {
    const summary = beginnerSummary(snapshot);
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <Callout tone={summary.ready ? 'success' : 'muted'} title={summary.text}>
          <p>{snapshot.local_runtime.detail}</p>
        </Callout>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Header onRefresh={state.reload} refreshing={state.refreshing} />
      <Panel title="Yerel AI">
        <div className="divide-y divide-slate-100">
          {readings(snapshot).map((reading) => (
            <DimensionRow key={reading.dimension} reading={reading} />
          ))}
        </div>
      </Panel>
    </div>
  );
}
