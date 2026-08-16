import { useEffect, useState } from 'react';

import { Button, Callout, Field, Panel } from '@/components/ui';
import type { WorkflowEdgeShape, WorkflowNodeShape } from '@/api/contracts';

/** Editable properties of whichever node or edge is currently selected. */
export function InspectorPanel({
  selectedNode,
  selectedEdge,
  onSetNodeLabel,
  onSetNodeParameters,
  onRemoveNode,
  onSetEdgeCondition,
  onRemoveEdge,
}: {
  selectedNode: WorkflowNodeShape | null;
  selectedEdge: WorkflowEdgeShape | null;
  onSetNodeLabel: (nodeId: string, label: string) => void;
  onSetNodeParameters: (nodeId: string, parameters: Record<string, unknown>) => void;
  onRemoveNode: (nodeId: string) => void;
  onSetEdgeCondition: (edgeId: string, condition: string | null) => void;
  onRemoveEdge: (edgeId: string) => void;
}) {
  const [parametersText, setParametersText] = useState('{}');
  const [parametersError, setParametersError] = useState<string | null>(null);

  useEffect(() => {
    setParametersText(selectedNode === null ? '{}' : JSON.stringify(selectedNode.parameters));
    setParametersError(null);
  }, [selectedNode?.node_id]);

  if (selectedNode !== null) {
    return (
      <Panel title="Node properties">
        <div className="flex flex-col gap-4">
          <p className="font-mono text-xs text-slate-500">{selectedNode.node_id}</p>
          <Field
            id="inspector-label"
            label="Label"
            value={selectedNode.label}
            onChange={(value) => onSetNodeLabel(selectedNode.node_id, value)}
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="inspector-parameters" className="text-sm font-medium text-slate-800">
              Parameters (JSON)
            </label>
            <textarea
              id="inspector-parameters"
              value={parametersText}
              rows={4}
              onChange={(event) => {
                const text = event.target.value;
                setParametersText(text);
                try {
                  const parsed: unknown = JSON.parse(text);
                  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
                    setParametersError('Parameters must be a JSON object.');
                    return;
                  }
                  setParametersError(null);
                  onSetNodeParameters(selectedNode.node_id, parsed as Record<string, unknown>);
                } catch {
                  setParametersError('Not valid JSON yet.');
                }
              }}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-900"
            />
            {parametersError === null ? null : (
              <Callout tone="muted" title={parametersError} />
            )}
          </div>
          <div>
            <Button onClick={() => onRemoveNode(selectedNode.node_id)}>Delete node</Button>
          </div>
        </div>
      </Panel>
    );
  }

  if (selectedEdge !== null) {
    return (
      <Panel title="Edge properties">
        <div className="flex flex-col gap-4">
          <p className="font-mono text-xs text-slate-500">{selectedEdge.edge_id}</p>
          <p className="text-sm text-slate-600">
            {selectedEdge.source_node_id} → {selectedEdge.target_node_id}
          </p>
          <Field
            id="inspector-condition"
            label="Condition"
            hint="A branch label such as true, false, or a SWITCH case. Leave blank for an unconditional edge."
            value={selectedEdge.condition ?? ''}
            onChange={(value) =>
              onSetEdgeCondition(selectedEdge.edge_id, value.trim() === '' ? null : value)
            }
          />
          <div>
            <Button onClick={() => onRemoveEdge(selectedEdge.edge_id)}>Delete edge</Button>
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <Panel title="Properties">
      <p className="text-sm text-slate-500">
        Select a node or an edge on the canvas to inspect and edit it.
      </p>
    </Panel>
  );
}
