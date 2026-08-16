/**
 * View state for the Visual Workflow Studio.
 *
 * THE DRAFT IS NOT THE AUTHORITY. `nodes`/`edges` here are a local canvas
 * draft the operator is composing; the only real C-20 graph is the revision
 * `WorkflowGraphStore` returns from a successful publish. This hook derives
 * no validity of its own — a graph that violates a canonical rule (a
 * dangling edge, an unreachable node, a `logic` node missing its construct)
 * is published anyway and shown exactly the refusal the backend gave, the
 * same "offer it, let the backend refuse it" discipline
 * `useProjectRegistry.ts` already uses for an illegal lifecycle transition.
 *
 * EXECUTION STATE IS NEVER INVENTED. `lifecycle_state`, `pending_approval_node_id`
 * and the evidence list are always the backend's last answer, replaced
 * wholesale after every start/signal/approve call — never patched locally.
 */

import { useCallback, useMemo, useState } from 'react';

import { ApiRefusal, ApiUnavailable, type ArkaliApiClient } from '@/api/client';
import type {
  WorkflowEdgeShape,
  WorkflowExecutionDetailResponse,
  WorkflowNodeShape,
  WorkflowRevisionDetailResponse,
} from '@/api/contracts';

export interface Failure {
  readonly code: string;
  readonly message: string;
}

function asFailure(error: unknown): Failure {
  if (error instanceof ApiRefusal) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof ApiUnavailable) {
    return { code: 'UNREACHABLE', message: error.message };
  }
  return { code: 'UNEXPECTED', message: 'An unexpected error occurred.' };
}

let counter = 0;
/** A locally-unique draft id. The published id is whatever the operator typed. */
function freshId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter}`;
}

export interface StudioState {
  readonly workflowId: string;
  readonly nodes: readonly WorkflowNodeShape[];
  readonly edges: readonly WorkflowEdgeShape[];
  readonly selectedNodeId: string | null;
  readonly selectedEdgeId: string | null;
  readonly pendingConnectionFrom: string | null;
  readonly revision: WorkflowRevisionDetailResponse | null;
  readonly loadingRevision: boolean;
  readonly publishing: boolean;
  readonly revisionFailure: Failure | null;
  readonly notice: string | null;
  readonly execution: WorkflowExecutionDetailResponse | null;
  readonly executionBusy: boolean;
  readonly executionFailure: Failure | null;
}

export interface StudioActions {
  setWorkflowId: (id: string) => void;
  loadLatest: () => Promise<void>;
  addNode: (kind: string, controlConstruct: string | null) => void;
  moveNode: (nodeId: string, positionX: number, positionY: number) => void;
  setNodeLabel: (nodeId: string, label: string) => void;
  setNodeParameters: (nodeId: string, parameters: Record<string, unknown>) => void;
  removeNode: (nodeId: string) => void;
  selectNode: (nodeId: string | null) => void;
  selectEdge: (edgeId: string | null) => void;
  beginConnection: (sourceNodeId: string) => void;
  completeConnection: (targetNodeId: string) => void;
  cancelConnection: () => void;
  setEdgeCondition: (edgeId: string, condition: string | null) => void;
  removeEdge: (edgeId: string) => void;
  publish: (semverBump: string) => Promise<void>;
  startExecution: (executionId: string) => Promise<void>;
  getExecution: (executionId: string) => Promise<void>;
  signalExecution: (executionId: string) => Promise<void>;
  approveExecution: (executionId: string, nodeId: string, actor: string) => Promise<void>;
  dismissNotice: () => void;
}

export function useWorkflowStudio(client: ArkaliApiClient): StudioState & StudioActions {
  const [workflowId, setWorkflowId] = useState('wf-studio');
  const [nodes, setNodes] = useState<readonly WorkflowNodeShape[]>([]);
  const [edges, setEdges] = useState<readonly WorkflowEdgeShape[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [pendingConnectionFrom, setPendingConnectionFrom] = useState<string | null>(null);
  const [revision, setRevision] = useState<WorkflowRevisionDetailResponse | null>(null);
  const [loadingRevision, setLoadingRevision] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [revisionFailure, setRevisionFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [execution, setExecution] = useState<WorkflowExecutionDetailResponse | null>(null);
  const [executionBusy, setExecutionBusy] = useState(false);
  const [executionFailure, setExecutionFailure] = useState<Failure | null>(null);

  const loadLatest = useCallback(async () => {
    setLoadingRevision(true);
    setRevisionFailure(null);
    setNotice(null);
    try {
      const detail = await client.getLatestWorkflowRevision(workflowId);
      setRevision(detail);
      setNodes(detail.nodes);
      setEdges(detail.edges);
      setSelectedNodeId(null);
      setSelectedEdgeId(null);
    } catch (error: unknown) {
      if (error instanceof ApiRefusal && error.status === 404) {
        // No revision published yet for this identifier — an honest empty
        // canvas, not a failure: the same reading `ProjectList` gives an
        // empty registry.
        setRevision(null);
        setNodes([]);
        setEdges([]);
      } else {
        setRevisionFailure(asFailure(error));
      }
    } finally {
      setLoadingRevision(false);
    }
  }, [client, workflowId]);

  const addNode = useCallback((kind: string, controlConstruct: string | null) => {
    const index = nodes.length;
    const node: WorkflowNodeShape = {
      node_id: freshId('node'),
      kind,
      control_construct: controlConstruct,
      label: controlConstruct ?? kind,
      parameters: {},
      position_x: 80 + (index % 4) * 200,
      position_y: 80 + Math.floor(index / 4) * 140,
    };
    setNodes((current) => [...current, node]);
    setSelectedNodeId(node.node_id);
  }, [nodes.length]);

  const moveNode = useCallback((nodeId: string, positionX: number, positionY: number) => {
    setNodes((current) =>
      current.map((node) =>
        node.node_id === nodeId
          ? { ...node, position_x: positionX, position_y: positionY }
          : node,
      ),
    );
  }, []);

  const setNodeLabel = useCallback((nodeId: string, label: string) => {
    setNodes((current) =>
      current.map((node) => (node.node_id === nodeId ? { ...node, label } : node)),
    );
  }, []);

  const setNodeParameters = useCallback((nodeId: string, parameters: Record<string, unknown>) => {
    setNodes((current) =>
      current.map((node) => (node.node_id === nodeId ? { ...node, parameters } : node)),
    );
  }, []);

  const removeNode = useCallback((nodeId: string) => {
    setNodes((current) => current.filter((node) => node.node_id !== nodeId));
    setEdges((current) =>
      current.filter((edge) => edge.source_node_id !== nodeId && edge.target_node_id !== nodeId),
    );
    setSelectedNodeId((current) => (current === nodeId ? null : current));
  }, []);

  const selectNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    setSelectedEdgeId(null);
  }, []);

  const selectEdge = useCallback((edgeId: string | null) => {
    setSelectedEdgeId(edgeId);
    setSelectedNodeId(null);
  }, []);

  const beginConnection = useCallback((sourceNodeId: string) => {
    setPendingConnectionFrom(sourceNodeId);
  }, []);

  const cancelConnection = useCallback(() => setPendingConnectionFrom(null), []);

  const completeConnection = useCallback(
    (targetNodeId: string) => {
      setPendingConnectionFrom((source) => {
        if (source === null || source === targetNodeId) {
          return null;
        }
        const edge: WorkflowEdgeShape = {
          edge_id: freshId('edge'),
          source_node_id: source,
          target_node_id: targetNodeId,
          condition: null,
        };
        setEdges((current) => [...current, edge]);
        setSelectedEdgeId(edge.edge_id);
        return null;
      });
    },
    [],
  );

  const setEdgeCondition = useCallback((edgeId: string, condition: string | null) => {
    setEdges((current) =>
      current.map((edge) => (edge.edge_id === edgeId ? { ...edge, condition } : edge)),
    );
  }, []);

  const removeEdge = useCallback((edgeId: string) => {
    setEdges((current) => current.filter((edge) => edge.edge_id !== edgeId));
    setSelectedEdgeId((current) => (current === edgeId ? null : current));
  }, []);

  const publish = useCallback(
    async (semverBump: string) => {
      setPublishing(true);
      setRevisionFailure(null);
      setNotice(null);
      try {
        const detail = await client.publishWorkflowRevision(workflowId, {
          nodes: [...nodes],
          edges: [...edges],
          semver_bump: semverBump,
        });
        setRevision(detail);
        setNodes(detail.nodes);
        setEdges(detail.edges);
        setNotice(
          `Revision ${detail.revision_number} (${detail.semver}) published for ${workflowId}.`,
        );
      } catch (error: unknown) {
        setRevisionFailure(asFailure(error));
      } finally {
        setPublishing(false);
      }
    },
    [client, workflowId, nodes, edges],
  );

  const startExecution = useCallback(
    async (executionId: string) => {
      setExecutionBusy(true);
      setExecutionFailure(null);
      try {
        const detail = await client.startWorkflowExecution(workflowId, {
          execution_id: executionId,
          revision_number: null,
        });
        setExecution(detail);
      } catch (error: unknown) {
        setExecutionFailure(asFailure(error));
      } finally {
        setExecutionBusy(false);
      }
    },
    [client, workflowId],
  );

  const getExecution = useCallback(
    async (executionId: string) => {
      setExecutionBusy(true);
      setExecutionFailure(null);
      try {
        const detail = await client.getWorkflowExecution(workflowId, executionId);
        setExecution(detail);
      } catch (error: unknown) {
        setExecutionFailure(asFailure(error));
      } finally {
        setExecutionBusy(false);
      }
    },
    [client, workflowId],
  );

  const signalExecution = useCallback(
    async (executionId: string) => {
      setExecutionBusy(true);
      setExecutionFailure(null);
      try {
        const detail = await client.signalWorkflowExecution(workflowId, executionId);
        setExecution(detail);
      } catch (error: unknown) {
        setExecutionFailure(asFailure(error));
      } finally {
        setExecutionBusy(false);
      }
    },
    [client, workflowId],
  );

  const approveExecution = useCallback(
    async (executionId: string, nodeId: string, actor: string) => {
      if (execution === null) {
        return;
      }
      setExecutionBusy(true);
      setExecutionFailure(null);
      try {
        const detail = await client.approveWorkflowExecution(workflowId, executionId, {
          node_id: nodeId,
          actor,
          decision: 'APPROVED',
          approved_revision_hash: execution.bound_revision_hash,
        });
        setExecution(detail);
      } catch (error: unknown) {
        setExecutionFailure(asFailure(error));
      } finally {
        setExecutionBusy(false);
      }
    },
    [client, workflowId, execution],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  return useMemo(
    () => ({
      workflowId,
      nodes,
      edges,
      selectedNodeId,
      selectedEdgeId,
      pendingConnectionFrom,
      revision,
      loadingRevision,
      publishing,
      revisionFailure,
      notice,
      execution,
      executionBusy,
      executionFailure,
      setWorkflowId,
      loadLatest,
      addNode,
      moveNode,
      setNodeLabel,
      setNodeParameters,
      removeNode,
      selectNode,
      selectEdge,
      beginConnection,
      completeConnection,
      cancelConnection,
      setEdgeCondition,
      removeEdge,
      publish,
      startExecution,
      getExecution,
      signalExecution,
      approveExecution,
      dismissNotice,
    }),
    [
      workflowId,
      nodes,
      edges,
      selectedNodeId,
      selectedEdgeId,
      pendingConnectionFrom,
      revision,
      loadingRevision,
      publishing,
      revisionFailure,
      notice,
      execution,
      executionBusy,
      executionFailure,
      loadLatest,
      addNode,
      moveNode,
      setNodeLabel,
      setNodeParameters,
      removeNode,
      selectNode,
      selectEdge,
      beginConnection,
      completeConnection,
      cancelConnection,
      setEdgeCondition,
      removeEdge,
      publish,
      startExecution,
      getExecution,
      signalExecution,
      approveExecution,
      dismissNotice,
    ],
  );
}
