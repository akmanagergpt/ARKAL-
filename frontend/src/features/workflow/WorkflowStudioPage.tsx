import { useState } from 'react';

import type { ArkaliApiClient } from '@/api/client';
import { Button, Callout, Field, Panel } from '@/components/ui';

import { ExecutionPanel } from './ExecutionPanel';
import { InspectorPanel } from './InspectorPanel';
import { NodePalette } from './NodePalette';
import { useWorkflowStudio } from './useWorkflowStudio';
import { WorkflowCanvas } from './WorkflowCanvas';

const SEMVER_BUMPS = ['PATCH', 'MINOR', 'MAJOR'];

export function WorkflowStudioPage({ client }: { client: ArkaliApiClient }) {
  const studio = useWorkflowStudio(client);
  const [semverBump, setSemverBump] = useState('PATCH');

  const selectedNode = studio.nodes.find((node) => node.node_id === studio.selectedNodeId) ?? null;
  const selectedEdge = studio.edges.find((edge) => edge.edge_id === studio.selectedEdgeId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Visual Workflow Studio</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          UI rendering and backend execution are two views of the same C-20 graph
          revision. What you compose here is only real once the backend accepts it
          as a publish, and only ran once the backend's executor says so.
        </p>
      </div>

      <Panel
        title="Workflow"
        actions={
          <div className="flex items-center gap-2">
            <select
              aria-label="Semver bump"
              value={semverBump}
              onChange={(event) => setSemverBump(event.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900"
            >
              {SEMVER_BUMPS.map((bump) => (
                <option key={bump} value={bump}>
                  {bump}
                </option>
              ))}
            </select>
            <Button
              variant="primary"
              busy={studio.publishing}
              onClick={() => void studio.publish(semverBump)}
              disabled={studio.nodes.length === 0}
            >
              Publish revision
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1">
              <Field
                id="workflow-id"
                label="Workflow identifier"
                value={studio.workflowId}
                onChange={studio.setWorkflowId}
              />
            </div>
            <Button busy={studio.loadingRevision} onClick={() => void studio.loadLatest()}>
              Load latest revision
            </Button>
          </div>

          {studio.notice === null ? null : (
            <Callout tone="success" title="Done">
              <p>{studio.notice}</p>
            </Callout>
          )}
          {studio.revisionFailure === null ? null : (
            <Callout tone="error" title="The operation was refused">
              <p>{studio.revisionFailure.message}</p>
              <p className="mt-1 font-mono text-xs">{studio.revisionFailure.code}</p>
            </Callout>
          )}
          {studio.revision === null ? (
            <p className="text-sm text-slate-500">
              No revision published for this identifier yet.
            </p>
          ) : (
            <p className="text-sm text-slate-600">
              Revision {studio.revision.revision_number} ({studio.revision.semver}) ·{' '}
              <span className="font-mono text-xs">{studio.revision.revision_hash}</span>
            </p>
          )}

          {studio.pendingConnectionFrom === null ? null : (
            <Callout tone="muted" title="Click a target node to connect it">
              <Button onClick={studio.cancelConnection}>Cancel</Button>
            </Callout>
          )}

          <WorkflowCanvas
            nodes={studio.nodes}
            edges={studio.edges}
            selectedNodeId={studio.selectedNodeId}
            selectedEdgeId={studio.selectedEdgeId}
            pendingConnectionFrom={studio.pendingConnectionFrom}
            onSelectNode={studio.selectNode}
            onSelectEdge={studio.selectEdge}
            onBeginConnection={studio.beginConnection}
            onCompleteConnection={studio.completeConnection}
            onMoveNode={studio.moveNode}
          />
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <NodePalette onAddNode={studio.addNode} />
        <InspectorPanel
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          onSetNodeLabel={studio.setNodeLabel}
          onSetNodeParameters={studio.setNodeParameters}
          onRemoveNode={studio.removeNode}
          onSetEdgeCondition={studio.setEdgeCondition}
          onRemoveEdge={studio.removeEdge}
        />
        <ExecutionPanel
          execution={studio.execution}
          busy={studio.executionBusy}
          failure={studio.executionFailure}
          onStart={(executionId) => void studio.startExecution(executionId)}
          onRefresh={(executionId) => void studio.getExecution(executionId)}
          onSignal={(executionId) => void studio.signalExecution(executionId)}
          onApprove={(executionId, nodeId, actor) =>
            void studio.approveExecution(executionId, nodeId, actor)
          }
        />
      </div>
    </div>
  );
}
