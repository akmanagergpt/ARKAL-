/**
 * AI Software Factory — real goal intake, read-only production history,
 * and a real "Uygulamayı Aç" for whichever candidate is ACCEPTED.
 *
 * THREE REAL THINGS, NOT ONE. "Yeni Uygulama" (`NewApplicationIntake`) is a
 * genuine write path: it calls the real `POST /api/factory/goals`. The
 * history stays exactly what it always was — `GET /api/factory/history`, a
 * read of the staged-generation pipeline's own ledgers, with no button
 * here that starts a new `golden-work-*` run. `CandidatePreview` is the
 * third: for a candidate whose real ledger state is exactly ACCEPTED, it
 * enqueues a real `candidate.preview` durable job (`usePreview.ts`) and,
 * once ready, links to the real running app — see
 * `engineering.candidate.preview.run_preview` for what "ready" actually
 * required. DEF-009 (`docs/build/OPEN_BLOCKERS.md`) still records that no
 * live orchestrator wires this repository's real staged-generation
 * pipeline to a Command Center trigger — that is unchanged by this; a
 * preview shows a candidate that already finished generating, it does not
 * start one.
 *
 * WHY THIS LIVES HERE, NOT ON "Uygulamalarım" (Yönetilen Ürünler). The
 * managed-product registry (`ProjectRegistry`) and the candidate ledger
 * that actually proves something is runnable (`CandidateLedger`) have no
 * canonical relationship — confirmed by direct search, not assumed. No
 * project in "Uygulamalarım" today resolves to an ACCEPTED candidate, so
 * "Uygulamayı Aç" is wired where a real runnable identity already exists
 * instead of being faked onto a registry entry that cannot back it.
 */

import type { ArkaliApiClient } from '@/api/client';
import type { FactoryCampaignSummary, FactoryCandidateSummary } from '@/api/contracts';
import { Button, Callout, PageHeader, Panel, Spinner, StateBadge } from '@/components/ui';

import { NewApplicationIntake } from './NewApplicationIntake';
import { useFactoryHistory } from './useFactoryHistory';
import { usePreview } from './usePreview';

//: Turkish UI projections of `usePreview`'s own real phase/state vocabulary
//: — never a second copy of the C-19 Job machine's states themselves
//: (`StateBadge` above already shows those raw, deliberately untranslated).
//: A phase or state this map does not name falls back to the raw value.
const PREVIEW_PHASE_TR: Readonly<Record<string, string>> = {
  workspace_allocated: 'Ortam ayrılıyor',
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
const PREVIEW_JOB_STATE_TR: Readonly<Record<string, string>> = {
  QUEUED: 'Sırada bekliyor',
  RUNNING: 'Hazırlanıyor',
  CHECKPOINTED: 'Hazırlanıyor',
  CANCELLED: 'Durduruldu',
  FAILED: 'Hazırlanamadı',
  SUCCEEDED: 'Hazır',
  DEAD_LETTER: 'Durduruldu',
};

function CandidatePreview({
  candidate,
  client,
  showTechnical,
}: {
  candidate: FactoryCandidateSummary;
  client: ArkaliApiClient;
  showTechnical: boolean;
}) {
  const preview = usePreview(client, candidate.candidate_id);
  const runnable = candidate.state === 'ACCEPTED';
  const latestCheckpoint = preview.checkpoints.at(-1);
  const latestPhase = latestCheckpoint === undefined ? null : latestCheckpoint.payload.phase;
  const phaseLabel = typeof latestPhase === 'string' ? PREVIEW_PHASE_TR[latestPhase] : null;
  const stateLabel = preview.job === null
    ? null
    : preview.stopRequested
      ? 'Durdurma isteği gönderildi…'
      : phaseLabel ?? PREVIEW_JOB_STATE_TR[preview.job.lifecycle_state] ?? preview.job.lifecycle_state;
  const frontendUrl = preview.checkpoints.find((c) => c.payload.phase === 'ready')?.payload.frontend_url;
  const isReady = preview.job?.lifecycle_state === 'SUCCEEDED'
    || (typeof frontendUrl === 'string' && preview.job?.lifecycle_state !== 'CANCELLED'
      && preview.job?.lifecycle_state !== 'FAILED');
  const isDone = preview.job !== null
    && ['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER'].includes(preview.job.lifecycle_state);

  return (
    <div className="flex flex-col gap-2 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-sm text-slate-800">{candidate.candidate_id}</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500">{candidate.recorded_at}</span>
          <StateBadge state={candidate.state} />
          {preview.job === null || preview.job.lifecycle_state === 'CANCELLED' ? (
            <Button
              variant="primary"
              busy={preview.starting}
              disabled={!runnable}
              title={runnable ? undefined : `Yalnızca kabul edilmiş (ACCEPTED) adaylar açılabilir — bu adayın durumu: ${candidate.state}`}
              onClick={() => void preview.open()}
            >
              Uygulamayı Aç
            </Button>
          ) : !isDone && !isReady ? (
            // Once ready, the panel below owns the one real "Durdur" —
            // rendering it here too would duplicate the same control.
            <Button
              busy={preview.cancelling}
              disabled={preview.stopRequested}
              onClick={() => void preview.stop()}
            >
              Durdur
            </Button>
          ) : null}
        </div>
      </div>
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
                <Button
                  busy={preview.cancelling}
                  disabled={preview.stopRequested}
                  onClick={() => void preview.stop()}
                >
                  {preview.stopRequested ? 'Durduruluyor…' : 'Durdur'}
                </Button>
              ) : null}
            </div>
          ) : null}
          {showTechnical ? (
            <p className="mt-2 font-mono text-xs text-slate-500">
              job_id: {preview.job.job_id} · lifecycle_state: {preview.job.lifecycle_state}
              {typeof frontendUrl === 'string' ? ` · url: ${frontendUrl}` : ''}
            </p>
          ) : null}
        </div>
      ) : null}
      {preview.failure !== null ? (
        <Callout tone="error" title="İstek gönderilemedi">
          <p>{preview.failure.message}</p>
        </Callout>
      ) : null}
    </div>
  );
}

function CampaignCard({ campaign }: { campaign: FactoryCampaignSummary }) {
  return (
    <Panel
      title={campaign.campaign_id}
      actions={<StateBadge state={campaign.status} />}
    >
      <div className="flex flex-col gap-4">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Aday bütçesi</dt>
            <dd className="font-mono text-slate-800">
              {campaign.consumed_candidates} / {campaign.max_new_candidates}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Süre bütçesi (sn)</dt>
            <dd className="font-mono text-slate-800">
              {Math.round(campaign.consumed_seconds)} / {Math.round(campaign.max_total_seconds)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">
              Parmak izi (fingerprint) tekrar sınırı
            </dt>
            <dd className="font-mono text-slate-800">{campaign.max_same_fingerprint_repeats}</dd>
          </div>
        </dl>
        {campaign.attempts.length === 0 ? (
          <p className="text-sm text-slate-500">Bu kampanyada henüz kayıtlı bir deneme yok.</p>
        ) : (
          <div className="divide-y divide-slate-100 border-t border-slate-100">
            {campaign.attempts.map((attempt) => (
              <div key={`${attempt.candidate_id}-${attempt.recorded_at}`} className="py-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-sm text-slate-800">{attempt.candidate_id}</span>
                  <StateBadge state={attempt.outcome} />
                </div>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                  <span>{Math.round(attempt.elapsed_seconds)} sn sürdü</span>
                  {attempt.fingerprint === null ? null : (
                    <span className="font-mono">iz: {attempt.fingerprint}</span>
                  )}
                  {attempt.failure_class === null ? null : (
                    <span>sınıf: {attempt.failure_class}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function Header({
  onRefresh,
  refreshing,
}: {
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <PageHeader
      title={<>AI Software Factory <span className="text-base font-normal text-slate-500">(Yapay Zekâ Yazılım Fabrikası)</span></>}
      subtitle="Yeni bir uygulama isteği gönderin veya gerçek `golden-work-*` üretim geçmişini görüntüleyin."
      actions={<Button onClick={onRefresh} busy={refreshing}>Yenile</Button>}
    />
  );
}

export function FactoryHistoryPage({
  client,
  showTechnical,
}: {
  client: ArkaliApiClient;
  showTechnical: boolean;
}) {
  const state = useFactoryHistory(client);

  if (state.loading) {
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <NewApplicationIntake client={client} showTechnical={showTechnical} />
        <div className="flex items-center justify-center rounded-xl border border-slate-200 bg-white py-16">
          <Spinner label="Üretim geçmişi yükleniyor…" />
        </div>
      </div>
    );
  }

  if (state.snapshot === null) {
    return (
      <div className="flex flex-col gap-6">
        <Header onRefresh={state.reload} refreshing={state.refreshing} />
        <NewApplicationIntake client={client} showTechnical={showTechnical} />
        <Callout tone="error" title="Üretim geçmişi okunamadı">
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

  const { snapshot } = state;
  const noCandidates = snapshot.candidates.length === 0;
  const noCampaigns = snapshot.campaigns.length === 0;

  return (
    <div className="flex flex-col gap-6">
      <Header onRefresh={state.reload} refreshing={state.refreshing} />

      <NewApplicationIntake client={client} showTechnical={showTechnical} />

      {state.stale ? (
        <Callout tone="error" title="Veri güncel değil">
          <p>
            Son yenileme denemesi başarısız oldu
            {state.failure === null ? '' : `: ${state.failure.message}`}. Aşağıdaki
            değerler en son başarılı okumadan gösteriliyor.
          </p>
        </Callout>
      ) : null}

      <Callout tone="muted" title="Aşağıdaki geçmiş salt okunurdur (read-only)">
        <p>
          Canlı bir orkestratör (orchestrator) veya sağlayıcı kaydı henüz yok
          (bkz. DEF-009, <code className="font-mono">docs/build/OPEN_BLOCKERS.md</code>).
          Aşağıdaki adaylar ve kampanyalar yalnızca üretim hattının kendi kayıt
          defterlerinden okunur; burada yeni bir `golden-work-*` çalışması
          başlatılamaz. Yukarıdaki "Yeni Uygulama" isteğiniz gerçektir ve
          gerçekten gönderilir — ancak bugün bu ortamda onu otomatik olarak
          işleyecek bir üretim kapasitesi bulunmuyor.
        </p>
      </Callout>

      <Panel title="Adaylar (Candidates)">
        {noCandidates ? (
          <p className="text-sm text-slate-500">Henüz kayıtlı bir aday yok.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {snapshot.candidates.map((candidate) => (
              <CandidatePreview
                key={candidate.candidate_id}
                candidate={candidate}
                client={client}
                showTechnical={showTechnical}
              />
            ))}
          </div>
        )}
      </Panel>

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-600">
          Kampanyalar (Campaigns)
        </h2>
        {noCampaigns ? (
          <p className="text-sm text-slate-500">Henüz kayıtlı bir kampanya yok.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {snapshot.campaigns.map((campaign) => (
              <CampaignCard key={campaign.campaign_id} campaign={campaign} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
