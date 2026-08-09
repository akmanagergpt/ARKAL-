import { useState } from 'react';

import type { ProjectDetailResponse } from '@/api/contracts';
import { Button, Callout, Field, Panel, Spinner, StateBadge } from '@/components/ui';

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

/**
 * The selected project, its revisions, and the two operations the slice offers.
 *
 * THE TRANSITION CONTROL OFFERS EVERY STATE THE MACHINE DECLARES. It does not
 * filter the list to the ones it believes are reachable, because reachability
 * is the Project state machine's answer and this component is not entitled to
 * pre-empt it. An illegal request is sent, refused by the backend, and the
 * refusal is shown. That is slower than a disabled button and it is correct.
 */
export function ProjectDetail({
  project,
  lifecycleStates,
  loading,
  submitting,
  failure,
  onTransition,
  onCreateRevision,
}: {
  project: ProjectDetailResponse | null;
  lifecycleStates: readonly string[];
  loading: boolean;
  submitting: boolean;
  failure: { code: string; message: string } | null;
  onTransition: (projectId: string, target: string) => Promise<void>;
  onCreateRevision: (projectId: string, revisionId: string) => Promise<void>;
}) {
  const [target, setTarget] = useState('');
  const [revisionId, setRevisionId] = useState('');

  if (loading) {
    return (
      <Panel title="Project detail">
        <p className="py-6 text-center">
          <Spinner label="Loading the project…" />
        </p>
      </Panel>
    );
  }

  if (project === null) {
    return (
      <Panel title="Project detail">
        {failure === null ? (
          <p className="py-6 text-center text-sm text-slate-500">
            Select a project to see its lifecycle state and revisions.
          </p>
        ) : (
          <Callout tone="error" title="The project could not be loaded">
            <p>{failure.message}</p>
            <p className="mt-1 font-mono text-xs opacity-80">{failure.code}</p>
          </Callout>
        )}
      </Panel>
    );
  }

  return (
    <Panel title="Project detail" actions={<StateBadge state={project.lifecycle_state} />}>
      <div className="flex flex-col gap-6">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Name</dt>
            <dd className="text-sm font-medium text-slate-900">{project.name}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Identifier</dt>
            <dd className="font-mono text-sm text-slate-900">{project.project_id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Registered</dt>
            <dd className="text-sm text-slate-700">{formatTimestamp(project.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Last change</dt>
            <dd className="text-sm text-slate-700">{formatTimestamp(project.updated_at)}</dd>
          </div>
        </dl>

        {failure === null ? null : (
          <Callout tone="error" title="The operation was refused">
            <p>{failure.message}</p>
            <p className="mt-1 font-mono text-xs opacity-80">{failure.code}</p>
          </Callout>
        )}

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Revisions</h3>
          {project.revisions.length === 0 ? (
            <p className="text-sm text-slate-500">
              No revisions recorded for this project yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[28rem] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th scope="col" className="py-1 pr-4 font-medium">#</th>
                    <th scope="col" className="py-1 pr-4 font-medium">Revision</th>
                    <th scope="col" className="py-1 pr-4 font-medium">Recorded</th>
                    <th scope="col" className="py-1 font-medium">Provenance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {project.revisions.map((revision) => (
                    <tr key={revision.revision_id}>
                      <td className="py-2 pr-4 font-mono text-slate-500">{revision.sequence}</td>
                      <td className="py-2 pr-4 font-mono text-slate-900">{revision.revision_id}</td>
                      <td className="py-2 pr-4 text-slate-700">
                        {formatTimestamp(revision.created_at)}
                      </td>
                      <td className="py-2 text-slate-700">{revision.provenance_ref ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
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
                label="New revision identifier"
                value={revisionId}
                onChange={setRevisionId}
                disabled={submitting}
              />
            </div>
            <Button type="submit" busy={submitting} disabled={revisionId.trim() === ''}>
              Record revision
            </Button>
          </form>
        </section>

        <section className="flex flex-col gap-2 border-t border-slate-200 pt-4">
          <h3 className="text-sm font-semibold text-slate-800">Lifecycle</h3>
          {lifecycleStates.length === 0 ? (
            <Callout tone="muted" title="Lifecycle vocabulary unavailable">
              <p>
                The state vocabulary could not be read from the Command Center API, so no
                transition can be requested. It is not reconstructed here.
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
                  Requested state
                </label>
                <select
                  id="transition-target"
                  value={target}
                  disabled={submitting}
                  onChange={(event) => setTarget(event.target.value)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 disabled:bg-slate-100"
                >
                  <option value="">Select a state…</option>
                  {lifecycleStates.map((state) => (
                    <option key={state} value={state}>
                      {state}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" variant="primary" busy={submitting} disabled={target === ''}>
                Request transition
              </Button>
              <p className="basis-full text-xs text-slate-500">
                Whether a move is permitted is decided by ARKALI, not by this screen.
                A refused request is reported above with the reason it was refused.
              </p>
            </form>
          )}
        </section>
      </div>
    </Panel>
  );
}
