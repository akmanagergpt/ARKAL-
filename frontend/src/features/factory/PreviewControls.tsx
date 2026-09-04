/**
 * Shared "Uygulamayı Aç" / "Durdur" rendering over a `usePreview` result —
 * extracted from `FactoryHistoryPage.tsx`'s own original `CandidatePreview`
 * so Product Detail's real preview bridge (D-029's own follow-on) reuses
 * the identical control and status panel rather than a second preview UI.
 * Every phase/state label rendered here is either a REAL, backed value
 * from `usePreview`'s own state or one of these two fixed translation
 * tables — never a fabricated progress step.
 */

import type { PreviewActions, PreviewState } from './usePreview';

import { Button, Callout, Spinner } from '@/components/ui';

//: Turkish UI projections of `usePreview`'s own real phase/state vocabulary
//: — never a second copy of the C-19 Job machine's states themselves.
//: A phase or state this map does not name falls back to the raw value.
export const PREVIEW_PHASE_TR: Readonly<Record<string, string>> = {
  workspace_allocated: 'Ortam ayrılıyor',
  restored_from_cache: 'Önceki kurulum yeniden kullanılıyor',
  backend_installed: 'Arka uç bağımlılıkları kuruldu',
  backend_started: 'Arka uç başlatıldı',
  frontend_installed: 'Ön yüz bağımlılıkları kuruluyor',
  frontend_built: 'Ön yüz derlendi',
  ready: 'Hazır',
  refused: 'Reddedildi',
  crashed: 'Bir sorun oluştu',
  stopped: 'Durduruldu',
  auto_stopped: 'Zaman aşımıyla durduruldu',
  cancelled_during_setup: 'Hazırlık sırasında durduruldu',
};
export const PREVIEW_JOB_STATE_TR: Readonly<Record<string, string>> = {
  QUEUED: 'Sırada bekliyor',
  RUNNING: 'Hazırlanıyor',
  CHECKPOINTED: 'Hazırlanıyor',
  CANCELLED: 'Durduruldu',
  FAILED: 'Hazırlanamadı',
  SUCCEEDED: 'Hazır',
  DEAD_LETTER: 'Durduruldu',
};

export function previewIsReady(preview: PreviewState): boolean {
  const frontendUrl = preview.checkpoints.find((c) => c.payload.phase === 'ready')?.payload.frontend_url;
  return preview.job?.lifecycle_state === 'SUCCEEDED'
    || (typeof frontendUrl === 'string' && preview.job?.lifecycle_state !== 'CANCELLED'
      && preview.job?.lifecycle_state !== 'FAILED');
}

export function previewIsDone(preview: PreviewState): boolean {
  return preview.job !== null
    && ['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER'].includes(preview.job.lifecycle_state);
}

/** The one real "Aç"/"Durdur" action — placed wherever the caller's own
 * layout needs it (a table row's action column, a detail page's header). */
export function PreviewActionButton({
  preview, runnable, runnableHint,
}: {
  preview: PreviewState & PreviewActions;
  runnable: boolean;
  runnableHint?: string | undefined;
}) {
  const isReady = previewIsReady(preview);
  const isDone = previewIsDone(preview);
  if (preview.job === null || preview.job.lifecycle_state === 'CANCELLED') {
    return (
      <Button
        variant="primary"
        busy={preview.starting}
        disabled={!runnable}
        title={runnable ? undefined : runnableHint}
        onClick={() => void preview.open()}
      >
        Uygulamayı Aç
      </Button>
    );
  }
  if (!isDone && !isReady) {
    // Once ready, the status panel below owns the one real "Durdur" —
    // rendering it here too would duplicate the same control.
    return (
      <Button busy={preview.cancelling} disabled={preview.stopRequested} onClick={() => void preview.stop()}>
        Durdur
      </Button>
    );
  }
  return null;
}

/** Real checkpoint-derived progress, the "Çalışan uygulamayı aç" link once
 * ready, and any real refusal — the status panel below the action button. */
export function PreviewStatusPanel({
  preview, showTechnical, technicalDetail,
}: {
  preview: PreviewState & PreviewActions;
  showTechnical: boolean;
  technicalDetail?: string | undefined;
}) {
  const latestCheckpoint = preview.checkpoints.at(-1);
  const latestPhase = latestCheckpoint === undefined ? null : latestCheckpoint.payload.phase;
  const phaseLabel = typeof latestPhase === 'string' ? PREVIEW_PHASE_TR[latestPhase] : null;
  const stateLabel = preview.job === null
    ? null
    : preview.stopRequested
      ? 'Durdurma isteği gönderildi…'
      : phaseLabel ?? (preview.job ? PREVIEW_JOB_STATE_TR[preview.job.lifecycle_state] ?? preview.job.lifecycle_state : null);
  const frontendUrl = preview.checkpoints.find((c) => c.payload.phase === 'ready')?.payload.frontend_url;
  const isReady = previewIsReady(preview);
  const isDone = previewIsDone(preview);

  return (
    <>
      {preview.job !== null ? (
        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
          {!isDone ? (
            <div className="flex items-center gap-2 text-slate-700">
              <Spinner />
              <span>{stateLabel}</span>
            </div>
          ) : preview.job.lifecycle_state === 'CANCELLED' ? (
            <p className="text-slate-600">Bu önizleme durduruldu.</p>
          ) : preview.job.lifecycle_state === 'FAILED' ? (
            <p className="text-rose-700">Uygulama hazırlanamadı: {stateLabel}</p>
          ) : null}
          {isReady && typeof frontendUrl === 'string' ? (
            <div className="mt-2 flex items-center gap-3">
              <a
                href={frontendUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
              >
                Çalışan uygulamayı aç ↗
              </a>
              {preview.job.lifecycle_state !== 'CANCELLED' ? (
                <Button busy={preview.cancelling} disabled={preview.stopRequested} onClick={() => void preview.stop()}>
                  {preview.stopRequested ? 'Durduruluyor…' : 'Durdur'}
                </Button>
              ) : null}
            </div>
          ) : null}
          {showTechnical && technicalDetail !== undefined ? (
            <p className="mt-2 font-mono text-xs text-slate-500">{technicalDetail}</p>
          ) : null}
        </div>
      ) : null}
      {preview.failure !== null ? (
        <Callout tone="error" title="İstek gönderilemedi">
          <p>{preview.failure.message}</p>
        </Callout>
      ) : null}
    </>
  );
}
