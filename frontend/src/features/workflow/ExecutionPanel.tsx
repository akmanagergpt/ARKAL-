import { useState } from 'react';

import { Button, Callout, Field, Panel, StateBadge } from '@/components/ui';
import type { WorkflowExecutionDetailResponse } from '@/api/contracts';

import type { Failure } from './useWorkflowStudio';

/**
 * Execution controls and evidence.
 *
 * Nothing here decides whether a pause is legitimate, whether a signal may
 * resume it, or whether an approval counts: every state shown is the
 * backend's last answer, and the WAIT/HUMAN APPROVAL affordances are only
 * offered when the execution the backend returned says it is actually
 * paused there — the machine decides, this panel reads.
 */
export function ExecutionPanel({
  execution,
  busy,
  failure,
  onStart,
  onRefresh,
  onSignal,
  onApprove,
}: {
  execution: WorkflowExecutionDetailResponse | null;
  busy: boolean;
  failure: Failure | null;
  onStart: (executionId: string) => void;
  onRefresh: (executionId: string) => void;
  onSignal: (executionId: string) => void;
  onApprove: (executionId: string, nodeId: string, actor: string) => void;
}) {
  const [executionId, setExecutionId] = useState('exec-studio-1');
  const [actor, setActor] = useState('human-reviewer');

  return (
    <Panel title="Execution">
      <div className="flex flex-col gap-4">
        <Field
          id="execution-id"
          label="Execution identifier"
          value={executionId}
          onChange={setExecutionId}
          disabled={busy}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            busy={busy}
            onClick={() => onStart(executionId)}
            disabled={executionId.trim() === ''}
          >
            Start execution
          </Button>
          <Button
            busy={busy}
            onClick={() => onRefresh(executionId)}
            disabled={executionId.trim() === ''}
          >
            Refresh
          </Button>
        </div>

        {failure === null ? null : <Callout tone="error" title="The operation was refused">
          <p>{failure.message}</p>
          <p className="mt-1 font-mono text-xs">{failure.code}</p>
        </Callout>}

        {execution === null ? (
          <p className="text-sm text-slate-500">No execution loaded yet.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <StateBadge state={execution.lifecycle_state} />
              <span className="font-mono text-xs text-slate-500">{execution.execution_id}</span>
            </div>

            {execution.lifecycle_state === 'WAITING_SIGNAL' ? (
              <div>
                <Button busy={busy} onClick={() => onSignal(execution.execution_id)}>
                  Send signal
                </Button>
              </div>
            ) : null}

            {execution.lifecycle_state === 'WAITING_APPROVAL' &&
            execution.pending_approval_node_id !== null ? (
              <div className="flex flex-wrap items-end gap-2 rounded-md border border-amber-300 bg-amber-50 p-3">
                <div className="flex-1">
                  <Field id="approver-actor" label="Actor" value={actor} onChange={setActor} />
                </div>
                <Button
                  variant="primary"
                  busy={busy}
                  disabled={actor.trim() === ''}
                  onClick={() =>
                    onApprove(
                      execution.execution_id,
                      execution.pending_approval_node_id ?? '',
                      actor.trim(),
                    )
                  }
                >
                  Approve {execution.pending_approval_node_id}
                </Button>
              </div>
            ) : null}

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-xs uppercase tracking-wide text-slate-500">
                    <th className="py-1 pr-3">#</th>
                    <th className="py-1 pr-3">Node</th>
                    <th className="py-1 pr-3">Kind</th>
                    <th className="py-1 pr-3">Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {execution.evidence.map((row) => (
                    <tr key={row.sequence} className="border-t border-slate-100">
                      <td className="py-1 pr-3">{row.sequence}</td>
                      <td className="py-1 pr-3">{row.node_id}</td>
                      <td className="py-1 pr-3">{row.kind}</td>
                      <td className="py-1 pr-3 font-mono text-xs">{row.outcome}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {execution.evidence.length === 0 ? (
                <p className="py-2 text-sm text-slate-500">No evidence recorded yet.</p>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
