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
/** Distance between the left edges of two steps side by side: a 236px card plus a 54px gap, so branches never touch. */
export const COLUMN_GAP = 290;
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

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * The viewport offset that brings `rect` fully into view at the current zoom with `pad` px clear, moving as little as possible
 * (a rect taller or wider than the canvas is aligned to its top-left). Null when it is already fully visible.
 * `covered` is an overlay drawn on the canvas (screen px, canvas origin: the overview and zoom buttons bottom-left): a rect
 * that would sit under it is lifted until it clears the overlay, as long as its top stays in view.
 */
export function panToReveal(
  rect: Box,
  viewport: { x: number; y: number; zoom: number },
  size: { width: number; height: number },
  pad = 24,
  covered?: Box,
): { x: number; y: number } | null {
  const screen = (vp: { x: number; y: number; zoom: number }) => ({
    left: rect.x * vp.zoom + vp.x,
    top: rect.y * vp.zoom + vp.y,
    w: rect.width * vp.zoom,
    h: rect.height * vp.zoom,
  });
  const under = (vp: { x: number; y: number; zoom: number }) => {
    if (!covered) return false;
    const r = screen(vp);
    return r.left < covered.x + covered.width && r.left + r.w > covered.x && r.top < covered.y + covered.height && r.top + r.h > covered.y;
  };
  if (isInView(rect, viewport, size) && !under(viewport)) return null;
  const { left, top, w, h } = screen(viewport);
  const shift = (start: number, len: number, avail: number): number => {
    if (len + 2 * pad > avail || start < pad) return pad - start;
    if (start + len > avail - pad) return avail - pad - (start + len);
    return 0;
  };
  const moved = { ...viewport, x: viewport.x + shift(left, w, size.width), y: viewport.y + shift(top, h, size.height) };
  if (covered && under(moved)) {
    const r = screen(moved);
    const lift = covered.y - pad - (r.top + r.h);
    if (lift < 0 && r.top + lift >= pad) moved.y += lift;
  }
  return { x: moved.x, y: moved.y };
}

/** True when `rect` (flow coordinates) sits fully inside the visible canvas, keeping `margin` px clear (none by default: only content that is actually cut off counts). */
export function isInView(
  rect: Box,
  viewport: { x: number; y: number; zoom: number },
  size: { width: number; height: number },
  margin = { top: 0, side: 0, bottom: 0 },
): boolean {
  const left = rect.x * viewport.zoom + viewport.x;
  const top = rect.y * viewport.zoom + viewport.y;
  const right = left + rect.width * viewport.zoom;
  const bottom = top + rect.height * viewport.zoom;
  return left >= margin.side && top >= margin.top && right <= size.width - margin.side && bottom <= size.height - margin.bottom;
}
