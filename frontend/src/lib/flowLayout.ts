/**
 * "Tidy layout": a simple layered layout for a flow. Every step sits one row below its deepest
 * predecessor, steps on the same row are spread sideways, and a step with one predecessor lines up
 * under it, so a straight run stays a vertical line and a branch fans out below its router.
 */

interface LayoutNode {
  id: string;
  position: { x: number; y: number };
}
interface LayoutEdge {
  source: string;
  target: string;
}

export const ROW_GAP = 150;
export const COLUMN_GAP = 260;
const ORIGIN_X = 250;
const ORIGIN_Y = 100;

/** New positions keyed by step id; nodes keep their order for ties so the result is stable. */
export function tidyPositions(nodes: LayoutNode[], edges: LayoutEdge[]): Record<string, { x: number; y: number }> {
  const ids = new Set(nodes.map((n) => n.id));
  const out = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target) || e.source === e.target) continue;
    out.set(e.source, [...(out.get(e.source) ?? []), e.target]);
    incoming.set(e.target, [...(incoming.get(e.target) ?? []), e.source]);
  }

  // Depth = longest path from a root; a back edge (loop) is ignored via the in-progress set.
  const depth = new Map<string, number>();
  const visiting = new Set<string>();
  const depthOf = (id: string): number => {
    const known = depth.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const parents = incoming.get(id) ?? [];
    const d = parents.length === 0 ? 0 : Math.max(...parents.map((p) => (visiting.has(p) ? -1 : depthOf(p)))) + 1;
    visiting.delete(id);
    depth.set(id, Math.max(d, 0));
    return Math.max(d, 0);
  };
  nodes.forEach((n) => depthOf(n.id));

  const rows = new Map<number, string[]>();
  for (const n of nodes) rows.set(depth.get(n.id) ?? 0, [...(rows.get(depth.get(n.id) ?? 0) ?? []), n.id]);

  const x = new Map<string, number>();
  const positions: Record<string, { x: number; y: number }> = {};
  for (const d of [...rows.keys()].sort((a, b) => a - b)) {
    const row = rows.get(d) ?? [];
    // Wanted column: the average of the predecessors already placed (their children are ordered by it).
    const wanted = row.map((id, i) => {
      const placed = (incoming.get(id) ?? []).map((p) => x.get(p)).filter((v): v is number => v !== undefined);
      return { id, want: placed.length ? placed.reduce((a, b) => a + b, 0) / placed.length : ORIGIN_X + i * COLUMN_GAP, i };
    });
    wanted.sort((a, b) => a.want - b.want || a.i - b.i);
    // Siblings of one parent fan out around it; then push right to keep a column's width apart.
    const siblingIndex = new Map<string, number>();
    const groups = new Map<string, string[]>();
    for (const w of wanted) {
      const key = (incoming.get(w.id) ?? []).slice().sort().join('|') || w.id;
      groups.set(key, [...(groups.get(key) ?? []), w.id]);
    }
    groups.forEach((members) => members.forEach((id, i) => siblingIndex.set(id, i - (members.length - 1) / 2)));
    let cursor = -Infinity;
    for (const w of wanted) {
      const target = w.want + (siblingIndex.get(w.id) ?? 0) * COLUMN_GAP;
      const placedX = Math.max(target, cursor + COLUMN_GAP);
      cursor = placedX;
      x.set(w.id, placedX);
    }
  }

  // Keep the first step where the flow starts so the picture does not drift sideways.
  const first = nodes[0] ? x.get(nodes[0].id) : undefined;
  const shift = first === undefined ? 0 : ORIGIN_X - first;
  for (const n of nodes) {
    positions[n.id] = { x: Math.round((x.get(n.id) ?? 0) + shift), y: ORIGIN_Y + (depth.get(n.id) ?? 0) * ROW_GAP };
  }
  return positions;
}
