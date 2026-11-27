/**
 * Branching nodes are driven by their outgoing edges, not by node-id selects.
 *
 * Edge meaning is `edge.data.route` (see FlowEdgeRoute in types/flow.types.ts); the React Flow
 * `sourceHandle` is the route id, except 'next' which is the default (id-less) handle. The serializer
 * recomputes on_true/on_false, approve_next/reject_next/timeout_next, foreach body and router options from them.
 */
import type { FlowEdgeRoute } from '../../types/flow.types';

export interface BranchHandle {
  /** Route written on the edge. */
  route: FlowEdgeRoute;
  /** React Flow handle id on the node (undefined = the default handle). */
  handleId: string | undefined;
  label: string;
  /** May stay unconnected without blocking save. */
  optional?: boolean;
}

const CONDITION: BranchHandle[] = [
  { route: 'true', handleId: 'true', label: 'Yes' },
  { route: 'false', handleId: 'false', label: 'No' },
];
/** Path taken when the facts cannot be known (backend `fallback_next`); shown only on a condition that has one. */
const CONDITION_FALLBACK: BranchHandle = { route: 'fallback', handleId: 'fallback', label: "Can't tell", optional: true };
const HUMAN: BranchHandle[] = [
  { route: 'approve', handleId: 'approve', label: 'Approved' },
  { route: 'reject', handleId: 'reject', label: 'Rejected' },
];
const HUMAN_TIMEOUT: BranchHandle = { route: 'timeout', handleId: 'timeout', label: 'Timed out', optional: true };
const FOREACH: BranchHandle[] = [
  { route: 'body', handleId: 'body', label: 'For each item' },
  // Its own handle id: an id-less handle would be taken for the first handle ('For each item') by React Flow.
  { route: 'next', handleId: 'next', label: 'When done', optional: true },
];

const WAIT_WITH_TIMEOUT: BranchHandle[] = [
  { route: 'next', handleId: 'next', label: 'Continued', optional: true },
  HUMAN_TIMEOUT,
];

/** Fixed branch handles of an action config (`type` is the canvas discriminator). */
export function branchHandlesFor(actionType: string | undefined, config?: Record<string, unknown>): BranchHandle[] {
  switch (actionType) {
    case 'condition':
      return config && config.fallback_next ? [...CONDITION, CONDITION_FALLBACK] : CONDITION;
    case 'human.approval':
      return config && config.timeout_ms ? [...HUMAN, HUMAN_TIMEOUT] : HUMAN;
    case 'foreach':
      return FOREACH;
    case 'wait': {
      // A Timed out path exists only while "until continued" has a time limit.
      const resume = (config?.resume ?? {}) as { timeout_ms?: unknown };
      return config?.mode === 'resume' && resume.timeout_ms ? WAIT_WITH_TIMEOUT : [];
    }
    default:
      return [];
  }
}

/** Whether a node type keeps a single free-form fan-out handle (router: one 'option' edge per path). */
export const ROUTER_HANDLE = 'option';

/** Steps whose paths are free-form `option` connections from one handle: Choose with AI and Choose by rules. */
export const isPathRouter = (type: string | undefined): boolean => type === 'router' || type === 'router-decision';

/** Colour family of a branch name pill. */
export type BranchTone = 'good' | 'bad' | 'warn' | 'loop' | 'neutral';

/** Tone of the pill drawn on a connection of this route. */
export function branchTone(route: FlowEdgeRoute): BranchTone {
  switch (route) {
    case 'true':
    case 'approve':
      return 'good';
    case 'false':
    case 'reject':
    case 'error':
      return 'bad';
    case 'timeout':
    case 'fallback':
      return 'warn';
    case 'body':
    case 'next':
      return 'loop';
    default:
      return 'neutral';
  }
}
