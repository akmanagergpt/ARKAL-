/**
 * The Operations page (`ARK-REQ-0396`, D-028).
 *
 * READ-ONLY. This page renders `GET /api/operations/snapshot` and nothing
 * else — no cancel, retry or delete mutation exists here, because none is
 * authorized: D-028 scoped Command Center's consumption of C-34 telemetry to
 * that one route. Every dimension is shown exactly as `DimensionReading.
 * state` reports it; a `NOT_CONFIGURED`/`NOT_APPLICABLE` reading is real
 * information; nothing is invented to fill it in.
 */

import type { ArkaliApiClient } from '@/api/client';
import type {
  DimensionReading,
  HardwareSnapshot,
  OperationsSnapshot,
  RuntimeSnapshot,
  StorageSnapshot,
} from '@/api/contracts';
import { Button, Callout, PageHeader, Panel, Spinner } from '@/components/ui';

import { DimensionRow } from './DimensionRow';
import { useOperationsSnapshot } from './useOperationsSnapshot';

function runtimeDimensions(snapshot: RuntimeSnapshot): DimensionReading[] {
  return [
    snapshot.jobs_active,
    snapshot.jobs_queued,
    snapshot.jobs_stuck,
    snapshot.workflows_active,
    snapshot.providers,
    snapshot.agents,
    snapshot.workers,
  ];
}

function hardwareDimensions(snapshot: HardwareSnapshot): DimensionReading[] {
  return [
    snapshot.cpu_logical_cores,
    snapshot.ram_total_bytes,
    snapshot.disk_free_bytes,
    snapshot.network_reachable,
    snapshot.gpu_present,
    snapshot.vram_total_bytes,
  ];
}

function storageDimensions(snapshot: StorageSnapshot): DimensionReading[] {
  return [snapshot.database_reachable, snapshot.database_size_bytes];
}

function allReadings(snapshot: OperationsSnapshot): DimensionReading[] {
  return [
    ...runtimeDimensions(snapshot.runtime),
    ...hardwareDimensions(snapshot.hardware),
    ...storageDimensions(snapshot.storage),
  ];
}

function relativeTime(atMs: number, nowMs: number): string {
  const seconds = Math.max(0, Math.round((nowMs - atMs) / 1000));
  if (seconds < 5) return 'az önce';
  if (seconds < 60) return `${seconds} saniye önce`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} dakika önce`;
  const hours = Math.round(minutes / 60);
  return `${hours} saat önce`;
}

const GROUPS: ReadonlyArray<{
  title: string;
  pick: (snapshot: OperationsSnapshot) => DimensionReading[];
}> = [
  { title: 'Çalışma zamanı', pick: (snapshot) => runtimeDimensions(snapshot.runtime) },
  { title: 'Donanım', pick: (snapshot) => hardwareDimensions(snapshot.hardware) },
  { title: 'Depolama', pick: (snapshot) => storageDimensions(snapshot.storage) },
];

function Header({
  onRefresh,
  refreshing = false,
  lastUpdatedAt,
}: {
  onRefresh?: () => void;
  refreshing?: boolean;
  lastUpdatedAt?: number | null;
}) {
  return (
    <PageHeader
      title="Operasyonlar"
      subtitle="Sistem ve çalışma durumu doğrudan ARKALI'nin canlı servislerinden okunur; burada hiçbir değer yeniden üretilmez."
      actions={onRefresh === undefined ? undefined : (
        <div className="flex items-center gap-3">
          {lastUpdatedAt == null ? null : (
            <span className="text-xs text-slate-500">
              Son güncelleme: {relativeTime(lastUpdatedAt, Date.now())}
            </span>
          )}
          <Button onClick={onRefresh} busy={refreshing}>
            Yenile
          </Button>
        </div>
      )}
    />
  );
}

export function OperationsPage({ client }: { client: ArkaliApiClient }) {
  const state = useOperationsSnapshot(client);

  if (state.loading) {
    return (
      <div className="flex flex-col gap-6">
        <Header />
        <div className="flex items-center justify-center rounded-xl border border-slate-200 bg-white py-16">
          <Spinner label="Operasyon verileri yükleniyor…" />
        </div>
      </div>
    );
  }

  if (state.snapshot === null) {
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <Callout tone="error" title="Operasyon verileri okunamadı">
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
  const readings = allReadings(snapshot);
  const empty = readings.length === 0;
  const notConfigured = !empty && readings.every((reading) => reading.state !== 'PASS');

  return (
    <div className="flex flex-col gap-6">
      <Header
        onRefresh={state.reload}
        refreshing={state.refreshing}
        lastUpdatedAt={state.lastUpdatedAt}
      />

      {state.stale ? (
        <Callout tone="error" title="Veri güncel değil">
          <p>
            Son yenileme denemesi başarısız oldu
            {state.failure === null ? '' : `: ${state.failure.message}`}. Aşağıdaki
            değerler en son başarılı okumadan gösteriliyor.
          </p>
        </Callout>
      ) : null}

      {empty ? (
        <Callout tone="muted" title="Veri yok">
          <p>Backend herhangi bir operasyon boyutu döndürmedi.</p>
        </Callout>
      ) : notConfigured ? (
        <Callout tone="muted" title="Henüz yapılandırılmamış">
          <p>
            Hiçbir operasyon boyutu şu anda etkin değil. Her boyutun durumu aşağıda
            ayrı ayrı gösteriliyor.
          </p>
        </Callout>
      ) : null}

      {empty ? null : (
        <div className="grid gap-4 lg:grid-cols-3">
          {GROUPS.map((group) => (
            <Panel key={group.title} title={group.title}>
              <div className="divide-y divide-slate-100">
                {group.pick(snapshot).map((reading) => (
                  <DimensionRow key={reading.dimension} reading={reading} />
                ))}
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
