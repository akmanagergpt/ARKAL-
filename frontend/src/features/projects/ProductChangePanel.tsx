/**
 * "Ne değiştirmek istiyorsunuz?" — the real natural-language Managed
 * Product change flow (D-030 V1): request → real progress → a live
 * preview of the PROPOSED change → "Kabul Et" / "Vazgeç".
 *
 * Every phase/state label here is either a real, backed value from
 * `useProductChange`'s own state or one of the fixed translation tables
 * below — never a fabricated progress step. Shown at every skill level:
 * this is the product's own core capability, not an internal detail —
 * `showTechnical` only ever adds raw identifiers alongside the same
 * Turkish chrome, matching `ProjectDetail.tsx`'s own discipline.
 */

import { useState } from 'react';

import { Button, Callout, Spinner } from '@/components/ui';
import type { ProductChangeActions, ProductChangeState } from './useProductChange';

//: Turkish projections of `prepare_modification`'s own real checkpoint
//: phases, plus the reused preview phases the same job emits once a
//: verified change reaches live review (`PreviewControls.PREVIEW_PHASE_TR`
//: covers install/build; the two tables are merged for display).
const CHANGE_PHASE_TR: Readonly<Record<string, string>> = {
  base_revision_resolved: 'Mevcut sürüm belirlendi',
  workspace_allocated: 'Çalışma alanı hazırlanıyor',
  source_inspected: 'Uygulama kaynak kodu inceleniyor',
  plan_ready: 'Değişiklik planı hazır',
  changes_applied: 'Değişiklikler uygulandı',
  verification_running: 'Değişiklikler kontrol ediliyor',
  verification_passed: 'Kontrol başarılı',
  verification_failed: 'Kontrol başarısız',
  restored_from_cache: 'Önceki kurulum yeniden kullanılıyor',
  backend_installed: 'Arka uç bağımlılıkları kuruldu',
  backend_started: 'Arka uç başlatıldı',
  frontend_installed: 'Ön yüz bağımlılıkları kuruluyor',
  frontend_built: 'Ön yüz derlendi',
  ready_for_review: 'İncelemeye hazır',
  promoted: 'Kabul edildi',
  rejected: 'Vazgeçildi',
  refused: 'Reddedildi',
  crashed: 'Bir sorun oluştu',
};

const DONE_STATES: ReadonlySet<string> = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER']);

export function ProductChangePanel({
  change, showTechnical,
}: {
  change: ProductChangeState & ProductChangeActions;
  showTechnical: boolean;
}) {
  const [requestText, setRequestText] = useState('');
  const isDone = change.job !== null && DONE_STATES.has(change.job.lifecycle_state);
  const isActive = change.job !== null && !isDone;
  // `change.ready` reflects the LAST `ready_for_review` checkpoint this job
  // ever recorded — it stays non-null forever once a cycle reaches it, even
  // after that same job later reaches a real terminal state. Only while the
  // job is still active does a stale ready checkpoint from an earlier real
  // cycle need to be told apart from this one; `readyNow` is that real,
  // current fact — never the mere historical presence of the checkpoint.
  const readyNow = isActive && change.ready !== null;
  const latestPhase = change.checkpoints.at(-1)?.payload.phase;
  const phaseLabel = typeof latestPhase === 'string' ? CHANGE_PHASE_TR[latestPhase] ?? latestPhase : null;

  return (
    <section className="flex flex-col gap-3 border-t border-slate-200 pt-4">
      <h3 className="text-sm font-semibold text-slate-800">Değişiklik iste</h3>
      <p className="text-xs text-slate-500">
        Uygulamada ne değiştirmek istediğinizi kendi cümlelerinizle yazın. ARKALI değişikliği
        hazırlayıp size önizleme olarak gösterecek; siz onaylamadan gerçek uygulamaya işlenmez.
      </p>

      {!isActive ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const text = requestText.trim();
            if (text === '') {
              return;
            }
            void change.start(text).then(() => setRequestText(''));
          }}
        >
          <textarea
            id="change-request-text"
            value={requestText}
            disabled={change.starting}
            onChange={(event) => setRequestText(event.target.value)}
            placeholder="Örn. Ana ekrandaki başlığı daha açıklayıcı hale getir"
            rows={3}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 disabled:bg-slate-100 disabled:text-slate-500"
          />
          <div>
            <Button
              type="submit" variant="primary" busy={change.starting}
              disabled={requestText.trim() === ''}
            >
              Değişikliği Başlat
            </Button>
          </div>
        </form>
      ) : null}

      {change.job !== null ? (
        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
          {isActive && !readyNow ? (
            <div className="flex items-center gap-2 text-slate-700">
              <Spinner />
              <span>{phaseLabel ?? 'Hazırlanıyor…'}</span>
            </div>
          ) : null}

          {readyNow && change.ready !== null && change.promoted === null ? (
            <div className="flex flex-col gap-2">
              <p className="text-slate-700">
                Önerilen değişiklik hazır. Uygulamaya işlemeden önce nasıl göründüğünü inceleyebilirsiniz.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <a
                  href={change.ready.frontendUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
                >
                  Önerilen değişikliği önizle ↗
                </a>
                <Button
                  variant="primary" busy={change.promoting}
                  disabled={change.rejecting}
                  onClick={() => void change.promote()}
                >
                  Kabul Et
                </Button>
                <Button busy={change.rejecting} disabled={change.promoting} onClick={() => void change.reject()}>
                  Vazgeç
                </Button>
              </div>
            </div>
          ) : null}

          {isDone && change.job.lifecycle_state === 'SUCCEEDED' ? (
            <p className="text-emerald-700">
              Değişiklik kabul edildi ve yeni bir sürüm olarak kaydedildi.
              {showTechnical && change.promoted !== null ? ` (${change.promoted.revision_id})` : null}
            </p>
          ) : null}

          {isDone && change.job.lifecycle_state === 'CANCELLED' ? (
            <p className="text-slate-600">Bu değişiklik isteğinden vazgeçildi.</p>
          ) : null}

          {isDone && change.job.lifecycle_state !== 'SUCCEEDED' && change.job.lifecycle_state !== 'CANCELLED' ? (
            <p className="text-rose-700">Değişiklik hazırlanamadı: {phaseLabel ?? change.job.lifecycle_state}</p>
          ) : null}

          {showTechnical ? (
            <p className="mt-2 font-mono text-xs text-slate-500">
              job_id: {change.job.job_id} · lifecycle_state: {change.job.lifecycle_state}
            </p>
          ) : null}
        </div>
      ) : null}

      {change.failure !== null ? (
        <Callout tone="error" title="İstek gönderilemedi">
          <p>{change.failure.message}</p>
          <p className="mt-1 font-mono text-xs opacity-80">{change.failure.code}</p>
        </Callout>
      ) : null}
    </section>
  );
}
