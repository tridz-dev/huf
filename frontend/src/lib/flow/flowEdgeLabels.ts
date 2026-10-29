import type { FlowEdge } from '../../types/flow.types';
import { edgeRoute } from '../../services/flowSerializer';

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

/** Ids of `rootId` and everything reachable from it by following edges. */
export function subtreeIds(rootId: string, edges: Array<Pick<FlowEdge, 'source' | 'target'>>): Set<string> {
  const seen = new Set<string>([rootId]);
  const stack = [rootId];
  while (stack.length) {
    const cur = stack.pop() as string;
    for (const e of edges) {
      if (e.source === cur && !seen.has(e.target)) {
        seen.add(e.target);
        stack.push(e.target);
      }
    }
  }
  return seen;
}

/**
 * A second branch target dropped in the same column as the first would sit on the line to it, so the new
 * path is drawn behind the first box. Returns how far to move the new target (and what hangs below it)
 * sideways so every branch of a step gets its own column; 0 when it already has room.
 */
export function branchColumnShift(
  targetX: number,
  siblingXs: number[],
  column = 280
): number {
  let x = targetX;
  let guard = 0;
  while (siblingXs.some((sx) => Math.abs(sx - x) < column * 0.6) && guard++ < 10) x += column;
  return x - targetX;
}
