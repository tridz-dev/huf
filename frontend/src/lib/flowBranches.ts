/**
 * Branching nodes are driven by their outgoing edges, not by node-id selects.
 *
 * Edge meaning is `edge.data.route` (see FlowEdgeRoute in types/flow.types.ts); the React Flow
 * `sourceHandle` is the route id, except 'next' which is the default (id-less) handle. The serializer
 * recomputes on_true/on_false, approve_next/reject_next/timeout_next, foreach body and router options from them.
 */
import type { FlowEdgeRoute } from '../types/flow.types';

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
  { route: 'true', handleId: 'true', label: 'True' },
  { route: 'false', handleId: 'false', label: 'False' },
];
const HUMAN: BranchHandle[] = [
  { route: 'approve', handleId: 'approve', label: 'Approved' },
  { route: 'reject', handleId: 'reject', label: 'Rejected' },
];
const HUMAN_TIMEOUT: BranchHandle = { route: 'timeout', handleId: 'timeout', label: 'Timed out', optional: true };
const FOREACH: BranchHandle[] = [
  { route: 'body', handleId: 'body', label: 'For each item' },
  { route: 'next', handleId: undefined, label: 'When done', optional: true },
];

/** Fixed branch handles of an action config (`type` is the canvas discriminator). */
export function branchHandlesFor(actionType: string | undefined, config?: Record<string, unknown>): BranchHandle[] {
  switch (actionType) {
    case 'condition':
      return CONDITION;
    case 'human.approval':
      return config && config.timeout_ms ? [...HUMAN, HUMAN_TIMEOUT] : HUMAN;
    case 'foreach':
      return FOREACH;
    default:
      return [];
  }
}

/** Whether a node type keeps a single free-form fan-out handle (router: one 'option' edge per path). */
export const ROUTER_HANDLE = 'option';
