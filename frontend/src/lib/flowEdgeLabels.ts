import type { FlowEdge } from '../types/flow.types';
import { edgeRoute } from '../services/flowSerializer';

/**
 * Router path names start as the target step's title and keep following that title when the step is
 * renamed, until the user edits the path name (then it no longer equals the old title and is left alone).
 * Returns the edges unchanged (same array) when nothing follows.
 */
export function followRenamedTarget(edges: FlowEdge[], nodeId: string, oldLabel: string, newLabel: string): FlowEdge[] {
  if (oldLabel === newLabel) return edges;
  let changed = false;
  const next = edges.map((e) => {
    if (e.target === nodeId && edgeRoute(e) === 'option' && e.label === oldLabel) {
      changed = true;
      return { ...e, label: newLabel };
    }
    return e;
  });
  return changed ? next : edges;
}
