/**
 * "Yeni Uygulama" — the real goal-intake form for the AI Software Factory.
 *
 * WHAT THIS REALLY DOES. Submits the user's own words to the real, already
 * shipped `POST /api/factory/goals` (`ProductionFactory.submit_goal`):
 * a deterministic blueprint derivation, then a real tier-routing decision
 * against a real, live-probed local-model capability
 * (`engineering.localai.capability_query`), then — only if both resolve —
 * a real durable job. Nothing here re-derives a blueprint, guesses at
 * routing, or invents a job.
 *
 * WHY PROGRESS IS DERIVED, NEVER STAGED. When a submission reaches
 * `queued`, this screen polls the real `GET /api/jobs/{job_id}` and
 * `GET /api/jobs/{job_id}/checkpoints` (`useFactoryIntake`) — the real C-19
 * job store, and the real checkpoints `scripts/run_factory_worker.py`
 * records as it hands the job to the unchanged, real
 * `generate_staged_model_product`. If no worker is running, the job simply
 * stays `QUEUED` and this screen says so honestly — it never shows a
 * staged "Backend hazırlanıyor… Arayüz hazırlanıyor…" animation over a job
 * nothing is processing.
 */

import { useState } from 'react';

import type { ArkaliApiClient } from '@/api/client';
import type {
  _FactoryIntakeResponse,
  _JobCheckpointResponse,
  _UnresolvedQuestionShape,
  JobReferenceResponse,
} from '@/api/contracts';
import { Button, Callout, Panel } from '@/components/ui';

import { useFactoryIntake } from './useFactoryIntake';

const UNRESOLVED_REASON_TR: Readonly<Record<string, string>> = {
  ambiguous: 'Açıklamanızda belirsiz bir ifade var (ör. "belki", "ya da").',
  contradictory: 'Açıklamanızın bir kısmı başka bir kısmıyla çelişiyor.',
  underspecified: 'Bu kısım yeterince açık değil ya da çok kısa.',
  missing_acceptance_criteria:
    'ARKALI bu ifadeden otomatik olarak doğrulanabilir bir kural çıkaramadı. ' +
    'Bugün yalnızca açık sayısal koşullar içeren, resmi şekilde yazılmış ' +
    'cümleleri anlayabiliyor (ör. "Sistem en az 500 ms içinde yanıt vermelidir").',
};

//: Turkish UI projections of the real durable-job lifecycle state and the
//: real `phase` a worker checkpointed — never a second lifecycle vocabulary.
//: A state or phase this map does not name falls back to showing the raw
//: value rather than inventing a label for it.
const JOB_STATE_TR: Readonly<Record<string, string>> = {
  QUEUED: 'İstek alındı, sırada bekliyor',
  RUNNING: 'Üretiliyor',
  CHECKPOINTED: 'Üretiliyor',
  PAUSED: 'Duraklatıldı',
  RESUMING: 'Devam ediyor',
  SUCCEEDED: 'Hazır',
  FAILED: 'Sorun oluştu',
  CANCELLED: 'İşlem durduruldu',
  DEAD_LETTER: 'İşlem durduruldu',
};
const CHECKPOINT_PHASE_TR: Readonly<Record<string, string>> = {
  claimed: 'Hazırlanıyor',
  generating: 'Üretiliyor',
  staged_generation_pass: 'İlk üretim aşaması tamamlandı',
  stage_failed: 'Üretim sırasında bir sorun bulundu',
  final_gate_failed: 'Son doğrulama sırasında bir sorun bulundu',
  interrupted: 'İşlem durduruldu',
  refused: 'Bu istek zaten daha önce üretilmiş bir uygulamayla eşleşiyor',
};
//: The real, automatic acceptance attempt `scripts/run_factory_worker.py`
//: now runs immediately after `staged_generation_pass` (F-0084) carries its
//: own real outcome string in the same checkpoint payload
//: (`payload.acceptance.outcome`) — read here, never re-derived or guessed.
//: Anything this map does not name (including a checkpoint recorded before
//: this wiring existed, which carries no `acceptance` key at all) falls
//: back to the honest "not yet verified" sentence already below, never a
//: false "hazır" claim.
const ACCEPTANCE_OUTCOME_TR: Readonly<Record<string, string>> = {
  GOLDEN_ACCEPTANCE_PASS: 'Otomatik kabul (acceptance) de başarıyla tamamlandı — uygulamanız hazır.',
  GOLDEN_ACCEPTANCE_FAILED: 'Otomatik kabul denemesi gerçek bir sorun buldu; uygulama henüz kabul edilmedi.',
  ACCEPTANCE_PLAN_INCOMPLETE:
    'Otomatik kabul, üretilen içerikten gerçek bir doğrulama planı çıkaramadı; uygulama henüz kabul edilmedi.',
  ACCEPTANCE_SCENARIO_INCOMPATIBLE:
    'Otomatik kabul, mevcut içerikle uyumlu bir senaryo bulamadı; uygulama henüz kabul edilmedi.',
  CANDIDATE_INTEGRITY_FAILED: 'Aday içeriği kayıtlı durumla eşleşmiyor; uygulama henüz kabul edilmedi.',
  ACCEPTANCE_ALREADY_IN_PROGRESS: 'Bu aday için zaten ayrı bir kabul denemesi sürüyor.',
  ACCEPTANCE_INTERRUPTED: 'Otomatik kabul denemesi tamamlanamadan kesintiye uğradı; uygulama henüz kabul edilmedi.',
  ACCEPTANCE_BRIDGE_ERROR:
    'Otomatik kabul denemesi başlatılırken beklenmeyen bir hata oluştu; uygulama henüz kabul edilmedi.',
};

function acceptanceOutcome(latest: _JobCheckpointResponse | null | undefined): string | null {
  const acceptance = latest?.payload.acceptance;
  if (acceptance === null || typeof acceptance !== 'object') {
    return null;
  }
  const outcome = (acceptance as Record<string, unknown>).outcome;
  return typeof outcome === 'string' ? outcome : null;
}

function unresolvedReason(kind: string, showTechnical: boolean): string {
  const friendly = UNRESOLVED_REASON_TR[kind];
  if (!showTechnical) {
    return friendly ?? 'Açıklamanızın bir kısmı otomatik olarak çözümlenemedi.';
  }
  return friendly === undefined ? kind : `${kind} — ${friendly}`;
}

function UnresolvedList({
  questions,
  showTechnical,
}: {
  questions: readonly _UnresolvedQuestionShape[];
  showTechnical: boolean;
}) {
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm">
      {questions.map((question, index) => (
        <li key={index}>
          {unresolvedReason(question.kind, showTechnical)}
          {showTechnical ? (
            <span className="block text-xs text-slate-500">{question.detail}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function ProgressCallout({
  job,
  checkpoints,
  showTechnical,
}: {
  job: JobReferenceResponse;
  checkpoints: readonly _JobCheckpointResponse[];
  showTechnical: boolean;
}) {
  const latest = checkpoints.length > 0 ? checkpoints[checkpoints.length - 1] : null;
  const phase = typeof latest?.payload.phase === 'string' ? latest.payload.phase : null;
  const label = (phase !== null ? CHECKPOINT_PHASE_TR[phase] : null)
    ?? JOB_STATE_TR[job.lifecycle_state]
    ?? job.lifecycle_state;
  const isDone = ['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER'].includes(job.lifecycle_state);
  const tone = job.lifecycle_state === 'SUCCEEDED'
    ? 'success'
    : job.lifecycle_state === 'FAILED' || job.lifecycle_state === 'DEAD_LETTER'
      ? 'error'
      : 'muted';

  return (
    <Callout tone={tone} title={label}>
      {job.lifecycle_state === 'QUEUED' ? (
        <p>
          İsteğiniz gerçek bir işe kaydedildi ve şu anda sırada bekliyor. Bu
          ortamda onu işleyecek bir arka plan süreci (worker) çalışmıyorsa,
          burada bekliyor kalır.
        </p>
      ) : !isDone ? (
        <p>Uygulamanız gerçek zamanlı olarak üretiliyor. Bu işlem birkaç dakika sürebilir.</p>
      ) : job.lifecycle_state === 'SUCCEEDED' ? (
        <p>
          İlk üretim aşaması ve son bütünlük kontrolü başarıyla tamamlandı.{' '}
          {acceptanceOutcome(latest) === 'GOLDEN_ACCEPTANCE_PASS'
            ? ACCEPTANCE_OUTCOME_TR.GOLDEN_ACCEPTANCE_PASS
            : (acceptanceOutcome(latest) !== null
              ? (ACCEPTANCE_OUTCOME_TR[acceptanceOutcome(latest) as string]
                ?? 'Otomatik kabul denemesi tamamlandı ancak uygulama henüz kabul edilmedi.')
              : 'Bu, uygulamanın tamamen doğrulandığı (kabul/acceptance) anlamına henüz gelmiyor.')}
        </p>
      ) : (
        <p>
          ARKALI gerçek üretim sırasında bir sorun buldu ve uygulamayı
          tamamlayamadı. Candidate elle düzeltilmedi, doğrulama kuralları
          gevşetilmedi — bu, gerçek ve dürüst bir sonuçtur.
        </p>
      )}
      {showTechnical ? (
        <div className="mt-2 space-y-1 font-mono text-xs opacity-80">
          <p>job_id: {job.job_id} · lifecycle_state: {job.lifecycle_state}</p>
          {checkpoints.map((checkpoint) => (
            <p key={checkpoint.sequence}>
              #{checkpoint.sequence}: {JSON.stringify(checkpoint.payload)}
            </p>
          ))}
        </div>
      ) : null}
    </Callout>
  );
}

function ResultCallout({
  result,
  showTechnical,
}: {
  result: _FactoryIntakeResponse;
  showTechnical: boolean;
}) {
  if (result.state === 'governed_stop') {
    return (
      <Callout tone="error" title="İsteğiniz otomatik olarak işlenemedi">
        <p>
          Açıklamanız şu anda ARKALI&apos;nın otomatik olarak anlayabileceği netlikte
          değil. Aşağıdaki noktaları netleştirip yeniden deneyebilirsiniz:
        </p>
        <div className="mt-2">
          <UnresolvedList questions={result.unresolved} showTechnical={showTechnical} />
        </div>
        {showTechnical ? (
          <p className="mt-2 font-mono text-xs opacity-80">
            goal_id: {result.goal_id} · blueprint_id: {result.blueprint_id}
          </p>
        ) : null}
      </Callout>
    );
  }

  if (result.state === 'escalated') {
    return (
      <Callout tone="muted" title="İsteğiniz insan onayı gerektiriyor">
        <p>
          Açıklamanız anlaşıldı, ancak ARKALI şu anda bu isteği kendiliğinden
          üretime alacak bir yapılandırmaya sahip değil (otomatik olarak
          çalışabilecek bir yapay zekâ kapasitesi tanımlı değil ya da bu host
          üzerinde bulunamadı). Bu, isteğinizin reddedildiği anlamına gelmez —
          üretim otomasyonu bu istek için etkinleştirilemedi.
        </p>
        {showTechnical ? (
          <p className="mt-2 font-mono text-xs opacity-80">
            goal_id: {result.goal_id} · blueprint_id: {result.blueprint_id} ·
            selected_tier: {result.selected_tier ?? '—'}
          </p>
        ) : null}
      </Callout>
    );
  }

  return (
    <Callout tone="success" title="İsteğiniz sıraya alındı">
      <p>Açıklamanız anlaşıldı ve gerçek bir işe kaydedildi.</p>
      {showTechnical ? (
        <p className="mt-2 font-mono text-xs opacity-80">
          durable_job_id: {result.durable_job_id ?? '—'}
        </p>
      ) : null}
    </Callout>
  );
}

export function NewApplicationIntake({
  client,
  showTechnical,
}: {
  client: ArkaliApiClient;
  showTechnical: boolean;
}) {
  const intake = useFactoryIntake(client);
  const [goalText, setGoalText] = useState('');

  const trimmed = goalText.trim();

  return (
    <Panel title={showTechnical ? 'Yeni Uygulama (Goal Intake)' : 'Yeni Uygulama'}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (trimmed === '' || intake.submitting) {
            return;
          }
          void intake.submit(trimmed);
        }}
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-application-goal" className="text-sm font-medium text-slate-800">
            Nasıl bir uygulama yapmak istiyorsunuz?
          </label>
          <textarea
            id="new-application-goal"
            value={goalText}
            disabled={intake.submitting}
            onChange={(event) => setGoalText(event.target.value)}
            rows={4}
            placeholder="Örneğin: Stoklarımı, giriş-çıkış işlemlerini ve kritik stok seviyelerini takip edebileceğim bir uygulama istiyorum."
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 disabled:bg-slate-100"
          />
          <p className="text-xs text-slate-500">
            Kendi cümlelerinizle, günlük dille yazabilirsiniz. Teknik bir terim
            bilmenize gerek yok.
          </p>
        </div>

        <div>
          <Button type="submit" variant="primary" busy={intake.submitting} disabled={trimmed === ''}>
            {intake.submitting ? 'Gönderiliyor…' : 'Uygulamayı Oluştur'}
          </Button>
        </div>

        {intake.failure === null ? null : (
          <Callout tone="error" title="İstek gönderilemedi">
            <p>{intake.failure.message}</p>
            <p className="mt-1 font-mono text-xs opacity-80">{intake.failure.code}</p>
          </Callout>
        )}

        {intake.result === null ? null : (
          <ResultCallout result={intake.result} showTechnical={showTechnical} />
        )}

        {intake.job === null ? null : (
          <ProgressCallout
            job={intake.job}
            checkpoints={intake.checkpoints}
            showTechnical={showTechnical}
          />
        )}
      </form>
    </Panel>
  );
}
