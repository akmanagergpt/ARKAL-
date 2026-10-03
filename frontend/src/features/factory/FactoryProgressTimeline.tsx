import type { _JobCheckpointResponse } from '@/api/contracts';

const STAGE_LABELS: Readonly<Record<string, string>> = {
  backend_contract: 'Veri ve API sözleşmesi hazırlanıyor',
  backend_schema: 'Veritabanı şeması oluşturuluyor',
  backend_implementation: 'Backend uygulanıyor',
  backend_cors_boundary: 'Backend erişim sınırları doğrulanıyor',
  backend_tests: 'Backend testleri hazırlanıyor',
  product_ux_spec: 'Ürün ve kullanıcı deneyimi planlanıyor',
  manifests: 'Çalıştırma bağımlılıkları hazırlanıyor',
  frontend_client: 'Frontend API bağlantısı kuruluyor',
  frontend_ui: 'Kullanıcı arayüzü oluşturuluyor',
  frontend_forms: 'Formlar ve kullanıcı işlemleri tamamlanıyor',
  frontend_tests: 'Frontend testleri hazırlanıyor',
};

const PHASE_LABELS: Readonly<Record<string, string>> = {
  claimed: 'Üretim işi worker tarafından alındı',
  generating: 'İzole ürün çalışma alanı hazırlandı',
  staged_generation_pass: 'Kod üretim aşamaları tamamlandı',
  final_gate_failed: 'Son ürün doğrulamasında sorun bulundu',
  stage_failed: 'Bir üretim aşaması doğrulamayı geçemedi',
  refused: 'Üretim güvenli biçimde durduruldu',
  interrupted: 'Üretim kesildi',
};

interface TimelineEvent {
  readonly sequence: number;
  readonly label: string;
  readonly detail: string | null;
  readonly recordedAt: string;
}

function eventFromCheckpoint(checkpoint: _JobCheckpointResponse): TimelineEvent | null {
  const phase = typeof checkpoint.payload.phase === 'string' ? checkpoint.payload.phase : null;
  if (phase === null) return null;

  if (phase === 'stage_started') {
    const stage = typeof checkpoint.payload.stage === 'string' ? checkpoint.payload.stage : '';
    return {
      sequence: checkpoint.sequence,
      label: STAGE_LABELS[stage] ?? `Üretim aşaması: ${stage || 'bilinmeyen'}`,
      detail: stage || null,
      recordedAt: checkpoint.recorded_at,
    };
  }

  const label = PHASE_LABELS[phase];
  if (label === undefined) return null;
  return {
    sequence: checkpoint.sequence,
    label,
    detail: null,
    recordedAt: checkpoint.recorded_at,
  };
}

export function FactoryProgressTimeline({
  checkpoints,
  showTechnical,
}: {
  checkpoints: readonly _JobCheckpointResponse[];
  showTechnical: boolean;
}) {
  const events = checkpoints
    .map(eventFromCheckpoint)
    .filter((event): event is TimelineEvent => event !== null);

  if (events.length === 0) return null;

  return (
    <section aria-label="Canlı üretim aşamaları" className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-widest text-blue-700">Canlı üretim</div>
          <h3 className="mt-1 font-semibold text-slate-900">Gerçek Factory ilerlemesi</h3>
        </div>
        <span className="rounded-full bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700">
          {events.length} gerçek kayıt
        </span>
      </div>
      <ol className="space-y-3">
        {events.map((event, index) => {
          const current = index === events.length - 1;
          return (
            <li key={event.sequence} className="flex gap-3">
              <span
                aria-hidden="true"
                className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${current ? 'bg-blue-600' : 'bg-emerald-500'}`}
              />
              <div className="min-w-0">
                <p className={`text-sm ${current ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>
                  {event.label}
                </p>
                {showTechnical ? (
                  <p className="mt-0.5 font-mono text-xs text-slate-500">
                    #{event.sequence}{event.detail !== null ? ` · ${event.detail}` : ''} · {event.recordedAt}
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="mt-3 text-xs text-slate-500">
        Bu liste animasyon değildir; yalnızca backend tarafından kaydedilmiş gerçek job checkpoint&apos;lerini gösterir.
      </p>
    </section>
  );
}
