// Display helpers for node pickers used as branch/loop targets (condition
// True/False, loop body/done). Kept pure so the picker logic can be unit-tested.

export interface BranchTargetNode {
  id: string;
  data: { label?: string };
}

export interface BranchTargetEdge {
  source?: string;
  target: string;
}

/**
 * Ids of every node that can reach `targetId` by following edges backwards.
 * Choosing one of these as a branch target routes execution back upstream,
 * i.e. creates a cycle.
 */
export function findUpstreamNodeIds(edges: BranchTargetEdge[], targetId: string | null | undefined): Set<string> {
  const visited = new Set<string>();
  if (!targetId) return visited;
  const queue = [targetId];
  while (queue.length) {
    const current = queue.shift()!;
    for (const e of edges) {
      if (e.target === current && e.source && !visited.has(e.source)) {
        visited.add(e.source);
        queue.push(e.source);
      }
    }
  }
  return visited;
}

/**
 * Option label for each candidate node. Nodes that share a display label (e.g.
 * two "Transform Data" nodes) get a short id suffix so they can be told apart;
 * unique labels are returned unchanged. Upstream targets (see
 * findUpstreamNodeIds) are still selectable but marked as creating a loop.
 */
export function buildBranchOptionLabels(
  nodes: BranchTargetNode[],
  upstreamIds: Set<string> = new Set(),
): Map<string, string> {
  const labelOf = (n: BranchTargetNode) => n.data.label || n.id;
  const counts = new Map<string, number>();
  for (const n of nodes) {
    counts.set(labelOf(n), (counts.get(labelOf(n)) ?? 0) + 1);
  }

  const result = new Map<string, string>();
  for (const n of nodes) {
    const label = labelOf(n);
    const shortId = n.id.length > 8 ? `${n.id.slice(0, 8)}…` : n.id;
    const base = (counts.get(label) ?? 0) > 1 ? `${label} · ${shortId}` : label;
    result.set(n.id, upstreamIds.has(n.id) ? `${base}  ↑ upstream — creates a loop` : base);
  }
  return result;
}
