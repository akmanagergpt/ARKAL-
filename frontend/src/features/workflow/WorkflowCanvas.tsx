/**
 * The graph canvas: real pointer-driven dragging, real click-to-connect.
 *
 * No graph-drawing library is used. The Studio's minimum obligation is that
 * a real browser session can compose a real graph — drag a node, connect two
 * nodes, publish, reload, and see the same layout come back — and plain
 * pointer events plus an SVG overlay prove that with nothing to configure,
 * bundle, or trust beyond the DOM the browser already gives every page.
 */

import { useRef } from 'react';

import type { WorkflowEdgeShape, WorkflowNodeShape } from '@/api/contracts';

const NODE_WIDTH = 168;
const NODE_HEIGHT = 60;
const CANVAS_HEIGHT = 560;

function center(node: WorkflowNodeShape): { x: number; y: number } {
  return { x: node.position_x + NODE_WIDTH / 2, y: node.position_y + NODE_HEIGHT / 2 };
}

function WorkflowNodeView({
  node,
  selected,
  isConnectionSource,
  onClick,
  onBeginConnection,
  onMove,
}: {
  node: WorkflowNodeShape;
  selected: boolean;
  isConnectionSource: boolean;
  onClick: (nodeId: string) => void;
  onBeginConnection: (nodeId: string) => void;
  onMove: (nodeId: string, x: number, y: number) => void;
}) {
  const drag = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    moved: boolean;
  } | null>(null);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Workflow node ${node.label}`}
      data-node-id={node.node_id}
      data-kind={node.kind}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = {
          startX: event.clientX,
          startY: event.clientY,
          originX: node.position_x,
          originY: node.position_y,
          moved: false,
        };
      }}
      onPointerMove={(event) => {
        const state = drag.current;
        if (state === null) {
          return;
        }
        const dx = event.clientX - state.startX;
        const dy = event.clientY - state.startY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
          state.moved = true;
        }
        if (state.moved) {
          onMove(node.node_id, Math.max(0, state.originX + dx), Math.max(0, state.originY + dy));
        }
      }}
      onPointerUp={() => {
        const state = drag.current;
        drag.current = null;
        if (state !== null && !state.moved) {
          onClick(node.node_id);
        }
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          onClick(node.node_id);
        }
      }}
      style={{
        position: 'absolute',
        left: node.position_x,
        top: node.position_y,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        touchAction: 'none',
      }}
      className={`flex cursor-grab select-none flex-col justify-center rounded-md border-2 bg-white px-3 py-2 text-left shadow-sm active:cursor-grabbing ${
        selected
          ? 'border-slate-900 ring-2 ring-slate-300'
          : isConnectionSource
            ? 'border-emerald-500'
            : 'border-slate-300'
      }`}
    >
      <span className="truncate text-sm font-medium text-slate-900">{node.label}</span>
      <span className="truncate text-xs text-slate-500">
        {node.kind}
        {node.control_construct === null ? '' : ` · ${node.control_construct}`}
      </span>
      <button
        type="button"
        aria-label={`Connect from ${node.label}`}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          onBeginConnection(node.node_id);
        }}
        className="absolute -bottom-2 -right-2 h-4 w-4 rounded-full border-2 border-white bg-slate-900 hover:bg-slate-700"
      />
    </div>
  );
}

export function WorkflowCanvas({
  nodes,
  edges,
  selectedNodeId,
  selectedEdgeId,
  pendingConnectionFrom,
  onSelectNode,
  onSelectEdge,
  onBeginConnection,
  onCompleteConnection,
  onMoveNode,
}: {
  nodes: readonly WorkflowNodeShape[];
  edges: readonly WorkflowEdgeShape[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  pendingConnectionFrom: string | null;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
  onBeginConnection: (nodeId: string) => void;
  onCompleteConnection: (nodeId: string) => void;
  onMoveNode: (nodeId: string, x: number, y: number) => void;
}) {
  const byId = new Map(nodes.map((node) => [node.node_id, node]));

  return (
    <div
      className="relative w-full overflow-auto rounded-md border border-slate-200 bg-slate-50 bg-[linear-gradient(to_right,#e2e8f0_1px,transparent_1px),linear-gradient(to_bottom,#e2e8f0_1px,transparent_1px)] bg-[size:24px_24px]"
      style={{ height: CANVAS_HEIGHT }}
    >
      {nodes.length === 0 ? (
        <p className="p-4 text-sm text-slate-500">
          No nodes yet. Add one from the palette to begin composing a graph.
        </p>
      ) : null}
      <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L10,5 L0,10 z" fill="#475569" />
          </marker>
        </defs>
        {edges.map((edge) => {
          const source = byId.get(edge.source_node_id);
          const target = byId.get(edge.target_node_id);
          if (source === undefined || target === undefined) {
            return null;
          }
          const from = center(source);
          const to = center(target);
          const midX = (from.x + to.x) / 2;
          const midY = (from.y + to.y) / 2;
          const selected = edge.edge_id === selectedEdgeId;
          return (
            <g key={edge.edge_id}>
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={selected ? '#0f172a' : '#94a3b8'}
                strokeWidth={selected ? 2.5 : 1.5}
                markerEnd="url(#arrow)"
              />
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="transparent"
                strokeWidth={12}
                className="pointer-events-auto cursor-pointer"
                role="button"
                aria-label={`Edge ${edge.edge_id}`}
                onClick={() => onSelectEdge(edge.edge_id)}
              />
              {edge.condition === null ? null : (
                <text
                  x={midX}
                  y={midY - 6}
                  textAnchor="middle"
                  className="pointer-events-none fill-slate-600 text-[11px]"
                >
                  {edge.condition}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {nodes.map((node) => (
        <WorkflowNodeView
          key={node.node_id}
          node={node}
          selected={node.node_id === selectedNodeId}
          isConnectionSource={node.node_id === pendingConnectionFrom}
          onClick={(nodeId) => {
            if (pendingConnectionFrom !== null && pendingConnectionFrom !== nodeId) {
              onCompleteConnection(nodeId);
            } else {
              onSelectNode(nodeId);
            }
          }}
          onBeginConnection={onBeginConnection}
          onMove={onMoveNode}
        />
      ))}
    </div>
  );
}
