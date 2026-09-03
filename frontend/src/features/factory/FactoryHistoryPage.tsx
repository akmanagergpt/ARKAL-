/**
 * AI Software Factory — real goal intake, plus read-only production history.
 *
 * TWO REAL THINGS, NOT ONE. "Yeni Uygulama" (`NewApplicationIntake`) is a
 * genuine write path: it calls the real `POST /api/factory/goals`. The
 * history below it stays exactly what it always was — `GET
 * /api/factory/history`, a read of the staged-generation pipeline's own
 * ledgers, with no button here that starts a new `golden-work-*` run.
 * DEF-009 (`docs/build/OPEN_BLOCKERS.md`) records that no live orchestrator
 * wires this repository's real staged-generation pipeline to a Command
 * Center trigger yet, and neither section claims otherwise — see
 * `NewApplicationIntake.tsx`'s own doc comment for exactly how far the
 * real intake path reaches today.
 */

import type { ArkaliApiClient } from '@/api/client';
import type { FactoryCampaignSummary, FactoryCandidateSummary } from '@/api/contracts';
import { Button, Callout, Panel, Spinner, StateBadge } from '@/components/ui';

import { NewApplicationIntake } from './NewApplicationIntake';
import { useFactoryHistory } from './useFactoryHistory';

function CandidateRow({ candidate }: { candidate: FactoryCandidateSummary }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-2.5">
      <span className="font-mono text-sm text-slate-800">{candidate.candidate_id}</span>
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-500">{candidate.recorded_at}</span>
        <StateBadge state={candidate.state} />
      </div>
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
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">
          AI Software Factory <span className="text-base font-normal text-slate-500">(Yapay Zekâ Yazılım Fabrikası)</span>
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Yeni bir uygulama isteği gönderin veya gerçek `golden-work-*`
          üretim geçmişini görüntüleyin.
        </p>
      </div>
      <Button onClick={onRefresh} busy={refreshing}>
        Yenile
      </Button>
    </div>
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
              <CandidateRow key={candidate.candidate_id} candidate={candidate} />
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
