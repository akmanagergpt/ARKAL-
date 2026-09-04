import { useState } from 'react';

import type { ArkaliApiClient } from '@/api/client';
import type { ProjectDetailResponse } from '@/api/contracts';
import { Button, Callout, Field, Panel, Spinner, StateBadge } from '@/components/ui';
import { PreviewActionButton, PreviewStatusPanel } from '@/features/factory/PreviewControls';
import { usePreview } from '@/features/factory/usePreview';

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

/** The same real derivation shape `CreateProjectForm.deriveProjectId` uses,
 * scoped to one project's own next real sequence number rather than a name
 * — a beginner never invents a raw revision identifier by hand; the
 * registry (never this function) still decides whether it is accepted. */
function deriveRevisionId(nextSequence: number): string {
  return `surum-${nextSequence}-${Date.now().toString(36)}`;
}

/**
 * The selected project, its revisions, and the two operations the slice offers.
 *
 * THE TRANSITION CONTROL OFFERS EVERY STATE THE MACHINE DECLARES. It does not
 * filter the list to the ones it believes are reachable, because reachability
 * is the Project state machine's answer and this component is not entitled to
 * pre-empt it. An illegal request is sent, refused by the backend, and the
 * refusal is shown. That is slower than a disabled button and it is correct.
 *
 * `showTechnical` only ever changes which VALUES are shown (raw identifiers,
 * raw state strings, a free-text revision id) — never the UI language. The
 * chrome around them stays Turkish in both modes, matching the rest of the
 * panel.
 */
export function ProjectDetail({
  project,
  lifecycleStates,
  loading,
  submitting,
  failure,
  onTransition,
  onCreateRevision,
  showTechnical,
  client,
}: {
  project: ProjectDetailResponse | null;
  lifecycleStates: readonly string[];
  loading: boolean;
  submitting: boolean;
  failure: { code: string; message: string } | null;
  onTransition: (projectId: string, target: string) => Promise<void>;
  onCreateRevision: (projectId: string, revisionId: string) => Promise<void>;
  showTechnical: boolean;
  client: ArkaliApiClient;
}) {
  const [target, setTarget] = useState('');
  const [revisionId, setRevisionId] = useState('');
  // Hooks run unconditionally, before the early returns below (React's own
  // rule) -- `''` when nothing is selected yet is a real, safe no-op
  // subject id `usePreview` itself refuses to fetch for, never a request
  // sent with an empty id.
  const preview = usePreview(client, project?.project_id ?? '', 'project');

  if (loading) {
    return (
      <Panel title="Uygulama Bilgileri">
        <p className="py-6 text-center">
          <Spinner label="Uygulama yükleniyor…" />
        </p>
      </Panel>
    );
  }

  if (project === null) {
    return (
      <Panel title="Uygulama Bilgileri">
        {failure === null ? (
          <p className="py-6 text-center text-sm text-slate-500">
            Durumunu ve sürümlerini görmek için bir uygulama seçin.
          </p>
        ) : (
          <Callout tone="error" title="Uygulama yüklenemedi">
            <p>{failure.message}</p>
            <p className="mt-1 font-mono text-xs opacity-80">{failure.code}</p>
          </Callout>
        )}
      </Panel>
    );
  }

  return (
    <Panel
      title="Uygulama Bilgileri"
      actions={<StateBadge state={project.lifecycle_state} />}
    >
      <div className="flex flex-col gap-6">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Ad</dt>
            <dd className="text-sm font-medium text-slate-900">{project.name}</dd>
          </div>
          {showTechnical ? <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Kimlik</dt>
            <dd className="font-mono text-sm text-slate-900">{project.project_id}</dd>
          </div> : null}
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Kayıt tarihi</dt>
            <dd className="text-sm text-slate-700">{formatTimestamp(project.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Son değişiklik</dt>
            <dd className="text-sm text-slate-700">{formatTimestamp(project.updated_at)}</dd>
          </div>
        </dl>

        <section className="flex flex-col gap-2 border-t border-slate-200 pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-800">Uygulama</h3>
            <PreviewActionButton preview={preview} runnable={true} />
          </div>
          <PreviewStatusPanel
            preview={preview}
            showTechnical={showTechnical}
            technicalDetail={preview.job === null ? undefined : (
              `job_id: ${preview.job.job_id} · lifecycle_state: ${preview.job.lifecycle_state}`
            )}
          />
        </section>

        {failure === null ? null : (
          <Callout tone="error" title="İşlem reddedildi">
            <p>{failure.message}</p>
            <p className="mt-1 font-mono text-xs opacity-80">{failure.code}</p>
          </Callout>
        )}

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Sürümler</h3>
          {project.revisions.length === 0 ? (
            <p className="text-sm text-slate-500">Bu uygulama için henüz sürüm kaydedilmedi.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[28rem] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th scope="col" className="py-1 pr-4 font-medium">#</th>
                    <th scope="col" className="py-1 pr-4 font-medium">Sürüm</th>
                    <th scope="col" className="py-1 pr-4 font-medium">Kayıt tarihi</th>
                    <th scope="col" className="py-1 font-medium">Kaynak</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {project.revisions.map((revision) => (
                    <tr key={revision.revision_id}>
                      <td className="py-2 pr-4 font-mono text-slate-500">{revision.sequence}</td>
                      <td className={`py-2 pr-4 ${showTechnical ? 'font-mono text-slate-900' : 'text-slate-700'}`}>{showTechnical ? revision.revision_id : `Sürüm ${revision.sequence}`}</td>
                      <td className="py-2 pr-4 text-slate-700">
                        {formatTimestamp(revision.created_at)}
                      </td>
                      <td className="py-2 text-slate-700">{showTechnical ? (revision.provenance_ref ?? '—') : 'ARKALI tarafından kaydedildi'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {showTechnical ? (
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (revisionId.trim() === '') {
                  return;
                }
                void onCreateRevision(project.project_id, revisionId.trim()).then(() =>
                  setRevisionId(''),
                );
              }}
            >
              <div className="min-w-[14rem] flex-1">
                <Field
                  id="new-revision-id"
                  label="Yeni sürüm tanımlayıcısı"
                  value={revisionId}
                  onChange={setRevisionId}
                  disabled={submitting}
                />
              </div>
              <Button type="submit" busy={submitting} disabled={revisionId.trim() === ''}>
                Sürümü kaydet
              </Button>
            </form>
          ) : (
            <div>
              <Button
                busy={submitting}
                onClick={() =>
                  void onCreateRevision(
                    project.project_id,
                    deriveRevisionId(project.revisions.length + 1),
                  )
                }
              >
                Yeni sürüm kaydet
              </Button>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-2 border-t border-slate-200 pt-4">
          <h3 className="text-sm font-semibold text-slate-800">Durum</h3>
          {lifecycleStates.length === 0 ? (
            <Callout tone="muted" title="Durum listesi alınamadı">
              <p>
                Olası durumlar Command Center API üzerinden okunamadı, bu yüzden bir durum
                değişikliği istenemiyor.
              </p>
            </Callout>
          ) : (
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (target === '') {
                  return;
                }
                void onTransition(project.project_id, target);
              }}
            >
              <div className="flex flex-col gap-1.5">
                <label htmlFor="transition-target" className="text-sm font-medium text-slate-800">
                  Yeni durum
                </label>
                <select
                  id="transition-target"
                  value={target}
                  disabled={submitting}
                  onChange={(event) => setTarget(event.target.value)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 disabled:bg-slate-100"
                >
                  <option value="">Bir durum seçin…</option>
                  {lifecycleStates.map((state) => (
                    <option key={state} value={state}>
                      {state}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" variant="primary" busy={submitting} disabled={target === ''}>
                Durumu değiştir
              </Button>
              <p className="basis-full text-xs text-slate-500">
                Bu değişikliğe izin verilip verilmeyeceğine bu ekran değil, ARKALI karar verir.
                İstek reddedilirse nedeni yukarıda gösterilir.
              </p>
            </form>
          )}
        </section>
      </div>
    </Panel>
  );
}
