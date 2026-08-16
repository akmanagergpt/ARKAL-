/**
 * Palette-only picklists for the Studio canvas.
 *
 * NOT A SHADOW OF THE CANONICAL VOCABULARY. `execution.workflow.GraphVocabulary`
 * parses the real node-kind and control-construct lists from the VDC, and
 * `WorkflowGraphDocument.build` is the only place either list is ever
 * enforced — a graph this file's picklist could not have produced would still
 * be refused there, and a construct the VDC adds tomorrow is only a stale
 * palette button away, never a silently-accepted graph. Publishing a small
 * `GET /api/workflows/vocabulary` route to avoid this was considered and
 * rejected: both `execution.workflow` and `surfaces.command` are already at
 * `max_public_surface_per_context` (40/40), and the lifecycle-picklist
 * precedent (`LifecycleMachineResponse`) exists because a stale *transition*
 * picklist could misinform legality; a stale *node-kind* picklist cannot,
 * because kind never decides what happens next — the control construct does,
 * and the backend evaluates that at execution time regardless of how the
 * node was drawn.
 */

export const NODE_KINDS: readonly string[] = [
  'trigger',
  'AI',
  'agent',
  'engineering',
  'logic',
  'data',
  'integration',
  'approval',
  'release',
  'notification',
];

export const CONTROL_CONSTRUCTS: readonly string[] = [
  'IF',
  'ELSE',
  'SWITCH',
  'LOOP',
  'PARALLEL',
  'MERGE',
  'WAIT',
  'RETRY',
  'ERROR HANDLER',
  'HUMAN APPROVAL',
];

export const LOGIC_KIND = 'logic';
