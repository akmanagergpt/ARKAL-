/**
 * "Yeni Uygulama" — the real goal-intake form for the AI Software Factory.
 *
 * WHAT THIS REALLY DOES. Submits the user's own words to the real, already
 * shipped `POST /api/factory/goals` (`ProductionFactory.submit_goal`):
 * a deterministic blueprint derivation, then a real tier-routing decision,
 * then — only if both resolve — a real durable job. Nothing here re-derives
 * a blueprint, guesses at routing, or invents a job.
 *
 * WHY THERE IS NO PROGRESS BAR. `select_execution_tier` can only reach an
 * automated tier through a `capability_id` that a live, configured
 * `capability_query` resolves `PASS` — and the real running Command Center
 * (`scripts/run_command_center.py`) wires `ProductionFactory` with none. So
 * every real submission today ends at `governed_stop` (the description
 * could not be fully resolved) or `escalated` (resolved, but nothing
 * automated is configured to build it) — never `queued`. Even in the
 * `queued` case, no worker in this repository consumes
 * `software_factory.production` jobs (`docs/build/OPEN_BLOCKERS.md`,
 * DEF-009), so a job would sit queued forever. Showing a staged "Backend
 * hazırlanıyor… Arayüz hazırlanıyor…" animation over any of that would be a
 * fabricated success this screen refuses to produce. What is shown instead
 * is the real terminal answer, honestly explained.
 */

import { useState } from 'react';

import type { ArkaliApiClient } from '@/api/client';
import type { _FactoryIntakeResponse, _UnresolvedQuestionShape } from '@/api/contracts';
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
          çalışabilecek bir yapay zekâ kapasitesi tanımlı değil). Bu, isteğinizin
          reddedildiği anlamına gelmez — üretim otomasyonu henüz bu ortamda
          etkinleştirilmedi.
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
      <p>
        Açıklamanız anlaşıldı ve gerçek bir işe kaydedildi. Ancak bu ortamda şu
        anda bu işi otomatik olarak işleyecek bir arka plan süreci
        bulunmuyor, bu yüzden burada bir ilerleme görünmeyecektir.
      </p>
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
      </form>
    </Panel>
  );
}
