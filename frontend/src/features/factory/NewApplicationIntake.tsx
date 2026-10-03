import { useEffect, useRef, useState } from 'react';

import type { ArkaliApiClient } from '@/api/client';
import type {
  _FactoryConversationMessage,
  _FactoryIntakeResponse,
  _JobCheckpointResponse,
  _UnresolvedQuestionShape,
  JobReferenceResponse,
} from '@/api/contracts';
import { Button, Callout, Panel } from '@/components/ui';

import { PreviewActionButton, PreviewStatusPanel, previewIsReady } from './PreviewControls';
import { usePreview } from './usePreview';
import { useFactoryIntake } from './useFactoryIntake';
import { ProductChangePanel } from '@/features/projects/ProductChangePanel';
import { useProductChange } from '@/features/projects/useProductChange';

const UNRESOLVED_REASON_TR: Readonly<Record<string, string>> = {
  ambiguous: 'Açıklamanızda belirsiz bir ifade var.',
  contradictory: 'Açıklamanızın bir kısmı başka bir kısmıyla çelişiyor.',
  underspecified: 'Bu kısım yeterince açık değil.',
  missing_acceptance_criteria:
    'Bu isteğin otomatik doğrulanabilmesi için ARKALI daha net bir davranış veya ölçü arıyor.',
};

const JOB_STATE_TR: Readonly<Record<string, string>> = {
  QUEUED: 'İstek alındı, sırada bekliyor',
  RUNNING: 'Üretiliyor',
  CHECKPOINTED: 'Üretiliyor',
  PAUSED: 'Duraklatıldı',
  RESUMING: 'Devam ediyor',
  SUCCEEDED: 'Doğrulama tamamlandı',
  FAILED: 'Sorun oluştu',
  CANCELLED: 'İşlem durduruldu',
  DEAD_LETTER: 'İşlem durduruldu',
};

const CHECKPOINT_PHASE_TR: Readonly<Record<string, string>> = {
  claimed: 'Üretim işi alındı',
  generating: 'Uygulama üretiliyor',
  staged_generation_pass: 'Kod üretimi tamamlandı',
  stage_failed: 'Kod üretiminde sorun bulundu',
  final_gate_failed: 'Son doğrulamada sorun bulundu',
  interrupted: 'İşlem durduruldu',
  refused: 'Bu istek üretime alınmadı',
};

const ACCEPTANCE_OUTCOME_TR: Readonly<Record<string, string>> = {
  GOLDEN_ACCEPTANCE_PASS: 'Gerçek runtime ve browser kabulü başarıyla tamamlandı.',
  GOLDEN_ACCEPTANCE_FAILED: 'Gerçek kabul sırasında bir sorun bulundu; uygulama hazır sayılmadı.',
  ACCEPTANCE_PLAN_INCOMPLETE: 'Gerçek kullanıcı yolculuğu için doğrulama planı tamamlanamadı.',
  ACCEPTANCE_SCENARIO_INCOMPATIBLE: 'Doğrulama senaryosu üretilen uygulamayla eşleşmedi.',
  CANDIDATE_INTEGRITY_FAILED: 'Üretilen adayın bütünlüğü doğrulanamadı.',
  ACCEPTANCE_ALREADY_IN_PROGRESS: 'Bu uygulama için başka bir kabul işlemi sürüyor.',
  ACCEPTANCE_INTERRUPTED: 'Kabul işlemi tamamlanmadan kesildi.',
  ACCEPTANCE_BRIDGE_ERROR: 'Kabul köprüsünde beklenmeyen bir sorun oluştu.',
};

function acceptanceData(latest: _JobCheckpointResponse | null): Record<string, unknown> | null {
  const value = latest?.payload.acceptance;
  return value !== null && typeof value === 'object'
    ? value as Record<string, unknown>
    : null;
}

function acceptanceOutcome(latest: _JobCheckpointResponse | null): string | null {
  const value = acceptanceData(latest)?.outcome;
  return typeof value === 'string' ? value : null;
}

function registeredProjectId(latest: _JobCheckpointResponse | null): string | null {
  const registration = acceptanceData(latest)?.managed_product_registration;
  if (registration === null || typeof registration !== 'object') return null;
  const value = (registration as Record<string, unknown>).project_id;
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

function isProductionApproved(latest: _JobCheckpointResponse | null): boolean {
  return acceptanceOutcome(latest) === 'GOLDEN_ACCEPTANCE_PASS';
}

function unresolvedReason(kind: string, showTechnical: boolean): string {
  const friendly = UNRESOLVED_REASON_TR[kind] ?? 'Açıklamanızın bir kısmı otomatik olarak çözümlenemedi.';
  return showTechnical && !(kind in UNRESOLVED_REASON_TR) ? `${kind} — ${friendly}` : friendly;
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
          {showTechnical ? <span className="block text-xs text-slate-500">{question.detail}</span> : null}
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
  const latest = checkpoints.at(-1) ?? null;
  const phase = typeof latest?.payload.phase === 'string' ? latest.payload.phase : null;
  const outcome = acceptanceOutcome(latest);
  const label = phase !== null
    ? CHECKPOINT_PHASE_TR[phase] ?? phase
    : JOB_STATE_TR[job.lifecycle_state] ?? job.lifecycle_state;
  const isDone = ['SUCCEEDED', 'FAILED', 'CANCELLED', 'DEAD_LETTER'].includes(job.lifecycle_state);

  return (
    <Callout
      tone={job.lifecycle_state === 'SUCCEEDED' && isProductionApproved(latest) ? 'success' : job.lifecycle_state === 'FAILED' ? 'error' : 'muted'}
      title={label}
    >
      {job.lifecycle_state === 'QUEUED' ? (
        <p>İsteğiniz gerçek bir işe kaydedildi ve worker tarafından alınmayı bekliyor.</p>
      ) : !isDone ? (
        <p>ARKALI uygulamayı gerçek üretim ve doğrulama hattında çalıştırıyor.</p>
      ) : job.lifecycle_state === 'SUCCEEDED' ? (
        <p>
          {outcome === null
            ? 'Üretim tamamlandı; kabul sonucu henüz görünmüyor.'
            : ACCEPTANCE_OUTCOME_TR[outcome] ?? 'Kabul işlemi tamamlandı.'}
        </p>
      ) : (
        <p>ARKALI gerçek üretim sırasında sorunu durdurdu; başarısız aday hazır olarak işaretlenmedi.</p>
      )}
      {showTechnical ? (
        <div className="mt-2 space-y-1 font-mono text-xs opacity-80">
          <p>job_id: {job.job_id} · lifecycle_state: {job.lifecycle_state}</p>
          {checkpoints.map((checkpoint) => (
            <p key={checkpoint.sequence}>#{checkpoint.sequence}: {JSON.stringify(checkpoint.payload)}</p>
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
      <Callout tone="error" title="Bir noktayı netleştirelim">
        <p>ARKALI bu isteği güvenilir şekilde üretime çevirmek için aşağıdaki noktayı çözemedi:</p>
        <div className="mt-2"><UnresolvedList questions={result.unresolved} showTechnical={showTechnical} /></div>
      </Callout>
    );
  }
  if (result.state === 'escalated') {
    return (
      <Callout tone="muted" title="Bu istek şu anda üretime alınamadı">
        <p>Yerel üretim kapasitesi bu isteği otomatik çalıştırmaya uygun değil. ARKALI sessizce başka bir sağlayıcıya geçmedi.</p>
      </Callout>
    );
  }
  return (
    <Callout tone="success" title="Üretim başlatıldı">
      <p>İstek gerçek Factory işine kaydedildi. Bundan sonraki durum yalnızca gerçek worker checkpoint'lerinden okunuyor.</p>
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
  const [messages, setMessages] = useState<readonly _FactoryConversationMessage[]>([]);
  const [draft, setDraft] = useState<string | null>(null);
  const [guidancePending, setGuidancePending] = useState(false);
  const [guidanceFailure, setGuidanceFailure] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const autoPreviewRef = useRef<string | null>(null);

  const preview = usePreview(client, projectId ?? '', 'project');
  const change = useProductChange(client, projectId ?? '');

  const trimmed = goalText.trim();
  const explicitProduce = draft !== null && /^(tamam|üret|başla|başlat|yap|onay|devam)\b/i.test(trimmed);

  useEffect(() => {
    const latest = intake.checkpoints.at(-1) ?? null;
    if (!isProductionApproved(latest)) return;
    const registered = registeredProjectId(latest);
    if (registered !== null) setProjectId(registered);
  }, [intake.checkpoints]);

  useEffect(() => {
    if (projectId === null || autoPreviewRef.current === projectId) return;
    if (preview.job !== null) return;
    autoPreviewRef.current = projectId;
    void preview.open();
  }, [projectId, preview]);

  const askArkali = async () => {
    if (trimmed === '' || guidancePending || intake.submitting) return;

    if (explicitProduce) {
      const next = [...messages, { role: 'user' as const, content: trimmed }];
      setMessages([...next, { role: 'assistant', content: 'Tamam. Üretimi başlatıyorum; sonucu gerçek runtime ve browser doğrulamasıyla kontrol edeceğim.' }]);
      setGoalText('');
      setDraft(null);
      setGuidanceFailure(null);
      await intake.submit(draft);
      return;
    }

    const next = [...messages, { role: 'user' as const, content: trimmed }];
    setMessages(next);
    setGoalText('');
    setGuidanceFailure(null);
    setGuidancePending(true);
    try {
      const response = await client.continueFactoryConversation({ messages: next });
      setMessages([...next, { role: 'assistant', content: response.assistant_message }]);
      setDraft(response.proposed_goal_text);
    } catch {
      setGuidanceFailure('Yerel Qwen şu anda yanıt veremedi. Biraz sonra yeniden deneyebilirsiniz.');
    } finally {
      setGuidancePending(false);
    }
  };

  const productionReady = previewIsReady(preview)
    && isProductionApproved(intake.checkpoints.at(-1) ?? null)
    && projectId !== null;

  return (
    <Panel title={showTechnical ? 'Uygulama Atölyesi (Factory)' : 'Uygulama Atölyesi'}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void askArkali();
        }}
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-application-goal" className="text-sm font-medium text-slate-800">
            ARKALI&apos;ya ne yaptırmak istiyorsunuz?
          </label>
          <textarea
            id="new-application-goal"
            value={goalText}
            disabled={guidancePending || intake.submitting}
            onChange={(event) => setGoalText(event.target.value)}
            rows={4}
            placeholder={
              projectId === null
                ? 'Örn. Görev takip uygulaması istiyorum; görev ekleyeyim, tamamlayayım, silebileyim ve kapatıp açınca verilerim kalsın.'
                : 'Uygulamada ne değiştirmek istiyorsunuz? Örn. Ana başlığı değiştir ve kartları daha sade yap.'
            }
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 disabled:bg-slate-100"
          />
          <p className="text-xs text-slate-500">
            {projectId === null
              ? 'Günlük dil kullanın. Teknik kararları ARKALI verir; eksik iş kuralı varsa yalnız onu sorar.'
              : 'Bu artık aynı uygulamanın çalışma alanı. Değişiklikleri doğal dille isteyebilirsiniz.'}
          </p>
        </div>

        <div>
          <Button type="submit" variant="primary" busy={guidancePending || intake.submitting} disabled={trimmed === ''}>
            {guidancePending ? 'ARKALI düşünüyor…' : intake.submitting ? 'Üretim başlatılıyor…' : explicitProduce ? 'Üretimi başlat' : 'Gönder'}
          </Button>
        </div>

        {messages.length > 0 ? (
          <div aria-label="ARKALI görüşmesi" className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-4">
            {messages.map((message, index) => (
              <div key={index} className={message.role === 'assistant' ? 'text-slate-800' : 'text-blue-900'}>
                <span className="font-semibold">{message.role === 'assistant' ? 'ARKALI' : 'Siz'}:</span>{' '}
                <span className="whitespace-pre-wrap">{message.content}</span>
              </div>
            ))}
          </div>
        ) : null}

        {guidanceFailure !== null ? (
          <Callout tone="error" title="Görüşme sürdürülemedi"><p>{guidanceFailure}</p></Callout>
        ) : null}

        {draft !== null ? (
          <div className="space-y-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
            <h3 className="font-semibold text-slate-900">Üretime hazır kapsam</h3>
            <p className="text-sm text-slate-700">
              ARKALI bu kapsamı üretim hattına dönüştürdü. Değişiklik istiyorsanız konuşmaya devam edin.
              Hazırsanız sadece <strong>“tamam, üret”</strong> yazmanız yeterli.
            </p>
            <pre className="whitespace-pre-wrap rounded bg-white p-3 text-xs text-slate-700">{draft}</pre>
          </div>
        ) : null}

        {intake.failure !== null ? (
          <Callout tone="error" title="Üretim başlatılamadı">
            <p>{intake.failure.message}</p>
            {showTechnical ? <p className="mt-1 font-mono text-xs opacity-80">{intake.failure.code}</p> : null}
          </Callout>
        ) : null}

        {intake.result !== null ? <ResultCallout result={intake.result} showTechnical={showTechnical} /> : null}

        {intake.job !== null ? (
          <ProgressCallout job={intake.job} checkpoints={intake.checkpoints} showTechnical={showTechnical} />
        ) : null}

        {projectId !== null && intake.job !== null && isProductionApproved(intake.checkpoints.at(-1) ?? null) ? (
          <section className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-widest text-emerald-700">Gerçek uygulama</div>
                <h3 className="mt-1 text-base font-semibold text-slate-900">Çalışan ürün çalışma alanı</h3>
              </div>
              <span className="rounded-full bg-emerald-100 px-2 py-1 text-xs font-semibold text-emerald-700">DOĞRULANDI</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <PreviewActionButton preview={preview} runnable={true} />
              <PreviewStatusPanel preview={preview} showTechnical={showTechnical} />
            </div>
            {previewIsReady(preview) ? (
              <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-xs text-slate-500">
                  <span>Canlı önizleme</span>
                  <span>Gerçek runtime</span>
                </div>
                <iframe
                  title="ARKALI üretilen uygulama canlı önizleme"
                  src={String(preview.checkpoints.find((checkpoint) => checkpoint.payload.phase === 'ready')?.payload.frontend_url ?? '')}
                  className="h-[520px] w-full bg-white"
                  sandbox="allow-forms allow-modals allow-popups allow-presentation allow-scripts allow-same-origin"
                />
              </div>
            ) : null}
          </section>
        ) : null}

        {projectId !== null ? <ProductChangePanel change={change} showTechnical={showTechnical} /> : null}

        {productionReady ? (
          <Callout tone="success" title="Uygulama canlı">
            <p>
              ARKALI artık sadece kod üretmedi; gerçek acceptance geçti, Managed Product olarak kaydedildi
              ve çalışan runtime üzerinden önizleme açıldı. Sonraki değişiklikler aynı ürün üzerinden
              izole edilip doğrulanacaktır.
            </p>
          </Callout>
        ) : null}
      </form>
    </Panel>
  );
}
