/**
 * Auto layout ("Tidy layout") for a flow: a layered layout in the Sugiyama style, kept small and pure (no React).
 *
 *   1. Layers: every step sits one row below its deepest predecessor; a back edge (a cycle) is ignored.
 *   2. Long connections get invisible stand-ins on the rows they skip, so a line has a lane of its own and never has to
 *      pass behind a step (the canvas then routes it down that lane with right angles).
 *   3. Order: branches keep their left-to-right order (Yes before No, Approved before Rejected, a loop's body before
 *      "When done"); the order only changes when that removes crossings.
 *   4. Columns: each row is placed as close to the middle of what it connects to as the spacing allows (least squares with
 *      a minimum gap, solved exactly), so a straight run stays one vertical line, a fan is centred under its step and a
 *      join sits under its parents.
 *
 * Rows are ROW_GAP apart and neighbours in a row COLUMN_GAP apart, so spacing is even everywhere.
 */

export interface LayoutNode {
  id: string;
  position: { x: number; y: number };
}
export interface LayoutEdge {
  source: string;
  target: string;
  /** Where this connection sits among its step's branches (0 = leftmost). Falls back to the order edges are listed in. */
  order?: number;
}

/** Distance between two rows: a 100px card, room for a 12px branch name (kept 12px on screen when zoomed out) and the arrow. */
export const ROW_GAP = 160;
/** Card width the layout plans for and the clear space kept between two cards side by side. */
export const CARD_WIDTH = 236;
export const CARD_GAP = 54;
/** Distance between the left edges of two steps side by side: a 236px card plus a 54px gap, so branches never touch. */
export const COLUMN_GAP = CARD_WIDTH + CARD_GAP;
export const ORIGIN_X = 250;
export const ORIGIN_Y = 100;
/** Width and gap of the invisible stand-in for a long connection. */
const LANE_WIDTH = 24;
const LANE_GAP = 40;
const SWEEPS = 6;
const MAX_PASSES = 200;

interface Item {
  key: string;
  real: boolean;
  layer: number;
  width: number;
  x: number;
  up: string[];
  down: string[];
}

const gap = (a: Item, b: Item) => (a.width + b.width) / 2 + (a.real && b.real ? CARD_GAP : LANE_GAP);

/** Closest placement of `want` (one per item, in order) that keeps `gaps[i]` between item i and i+1: pool adjacent violators. */
function placeRow(want: number[], gaps: number[]): number[] {
  const offsets: number[] = [0];
  for (let i = 1; i < want.length; i++) offsets.push(offsets[i - 1] + gaps[i - 1]);
  const blocks: Array<{ sum: number; count: number }> = [];
  want.forEach((w, i) => {
    blocks.push({ sum: w - offsets[i], count: 1 });
    while (blocks.length > 1) {
      const last = blocks[blocks.length - 1];
      const prev = blocks[blocks.length - 2];
      if (prev.sum / prev.count <= last.sum / last.count) break;
      blocks.splice(blocks.length - 2, 2, { sum: prev.sum + last.sum, count: prev.count + last.count });
    }
  });
  const out: number[] = [];
  let i = 0;
  for (const b of blocks) for (let k = 0; k < b.count; k++, i++) out.push(b.sum / b.count + offsets[i]);
  return out;
}

const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length;

/** Number of pairs of connections between two rows that cross, given each row's order. */
function crossings(layers: string[][], items: Map<string, Item>): number {
  let total = 0;
  for (let l = 0; l + 1 < layers.length; l++) {
    const pos = new Map(layers[l + 1].map((k, i) => [k, i]));
    const ends: number[] = [];
    for (const k of layers[l]) {
      const targets = (items.get(k)?.down ?? []).map((t) => pos.get(t)).filter((v): v is number => v !== undefined).sort((a, b) => a - b);
      ends.push(...targets);
    }
    for (let i = 0; i < ends.length; i++) for (let j = i + 1; j < ends.length; j++) if (ends[i] > ends[j]) total++;
  }
  return total;
}

/** New positions keyed by step id. Every step keeps its place in `nodes` for ties, so the result is stable. */
export function autoLayout(nodes: LayoutNode[], edges: LayoutEdge[]): Record<string, { x: number; y: number }> {
  const ids = nodes.map((n) => n.id);
  const known = new Set(ids);
  const seen = new Set<string>();
  const list: LayoutEdge[] = [];
  edges.forEach((e, i) => {
    const key = `${e.source}>${e.target}`;
    if (!known.has(e.source) || !known.has(e.target) || e.source === e.target || seen.has(key)) return;
    seen.add(key);
    list.push({ ...e, order: e.order ?? i / 1000 });
  });
  const outgoing = new Map<string, LayoutEdge[]>();
  const incoming = new Map<string, number>();
  for (const e of list) {
    outgoing.set(e.source, [...(outgoing.get(e.source) ?? []), e]);
    incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);
  }
  for (const [, out] of outgoing) out.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

  // 1. Depth-first from the roots: visiting order, and the back edges (cycles) to leave out.
  const state = new Map<string, 'open' | 'done'>();
  const visit: string[] = [];
  const back = new Set<string>();
  const walk = (id: string) => {
    state.set(id, 'open');
    visit.push(id);
    for (const e of outgoing.get(id) ?? []) {
      const s = state.get(e.target);
      if (s === 'open') back.add(`${e.source}>${e.target}`);
      else if (!s) walk(e.target);
    }
    state.set(id, 'done');
  };
  for (const id of ids) if (!incoming.has(id) && !state.has(id)) walk(id);
  for (const id of ids) if (!state.has(id)) walk(id);
  const forward = list.filter((e) => !back.has(`${e.source}>${e.target}`));

  // 2. Layers: longest path from a root (visiting order is a valid order once back edges are gone).
  const layerOf = new Map<string, number>(ids.map((id) => [id, 0]));
  const byTarget = new Map<string, LayoutEdge[]>();
  forward.forEach((e) => byTarget.set(e.target, [...(byTarget.get(e.target) ?? []), e]));
  const topo: string[] = [];
  const indegree = new Map(ids.map((id) => [id, (byTarget.get(id) ?? []).length]));
  const queue = ids.filter((id) => indegree.get(id) === 0);
  const fwdOut = new Map<string, LayoutEdge[]>();
  forward.forEach((e) => fwdOut.set(e.source, [...(fwdOut.get(e.source) ?? []), e]));
  while (queue.length) {
    const id = queue.shift() as string;
    topo.push(id);
    for (const e of fwdOut.get(id) ?? []) {
      layerOf.set(e.target, Math.max(layerOf.get(e.target) ?? 0, (layerOf.get(id) ?? 0) + 1));
      indegree.set(e.target, (indegree.get(e.target) ?? 1) - 1);
      if (indegree.get(e.target) === 0) queue.push(e.target);
    }
  }

  // 3. Items: the steps plus a stand-in on every row a connection skips.
  const items = new Map<string, Item>();
  const layers: string[][] = [];
  const add = (item: Item) => {
    items.set(item.key, item);
    (layers[item.layer] ??= []).push(item.key);
  };
  const order = new Map(visit.map((id, i) => [id, i]));
  [...ids].sort((a, b) => (order.get(a) ?? 0) - (order.get(b) ?? 0)).forEach((id) => add({ key: id, real: true, layer: layerOf.get(id) ?? 0, width: CARD_WIDTH, x: 0, up: [], down: [] }));
  forward.forEach((e, n) => {
    const from = layerOf.get(e.source) ?? 0;
    const to = layerOf.get(e.target) ?? 0;
    let prev = e.source;
    for (let l = from + 1; l < to; l++) {
      const key = `~${n}:${l}`;
      add({ key, real: false, layer: l, width: LANE_WIDTH, x: 0, up: [], down: [] });
      items.get(prev)?.down.push(key);
      items.get(key)?.up.push(prev);
      prev = key;
    }
    items.get(prev)?.down.push(e.target);
    items.get(e.target)?.up.push(prev);
  });
  for (let l = 0; l < layers.length; l++) layers[l] ??= [];

  // 4. Order within rows: branch order from the walk; sweeps by neighbour position only when they remove crossings.
  let best = crossings(layers, items);
  for (let s = 0; s < SWEEPS && best > 0; s++) {
    const trial = layers.map((row) => row.slice());
    const sweep = (l: number, neighbours: (i: Item) => string[], rowOf: string[]) => {
      const at = new Map(rowOf.map((k, i) => [k, i]));
      const score = new Map(trial[l].map((k, i) => {
        const ns = neighbours(items.get(k) as Item).map((n) => at.get(n)).filter((v): v is number => v !== undefined);
        return [k, ns.length ? mean(ns) : i] as const;
      }));
      trial[l] = trial[l].map((k, i) => ({ k, i })).sort((a, b) => (score.get(a.k) ?? 0) - (score.get(b.k) ?? 0) || a.i - b.i).map((v) => v.k);
    };
    if (s % 2 === 0) for (let l = 1; l < trial.length; l++) sweep(l, (i) => i.up, trial[l - 1]);
    else for (let l = trial.length - 2; l >= 0; l--) sweep(l, (i) => i.down, trial[l + 1]);
    const c = crossings(trial, items);
    if (c < best) {
      best = c;
      trial.forEach((row, l) => { layers[l] = row; });
    }
  }

  // 5. Columns.
  for (const row of layers) {
    let x = 0;
    row.forEach((k, i) => {
      const item = items.get(k) as Item;
      if (i > 0) x += gap(items.get(row[i - 1]) as Item, item);
      item.x = x;
    });
  }
  // Returns how far the row moved, so the passes can stop once the picture has stopped changing.
  const settle = (l: number, neighbours: (i: Item) => string[]): number => {
    const row = layers[l];
    if (row.length === 0) return 0;
    const want = row.map((k) => {
      const item = items.get(k) as Item;
      const ns = neighbours(item).map((n) => (items.get(n) as Item).x);
      return ns.length ? mean(ns) : item.x;
    });
    const gaps = row.slice(1).map((k, i) => gap(items.get(row[i]) as Item, items.get(k) as Item));
    let moved = 0;
    placeRow(want, gaps).forEach((x, i) => {
      const item = items.get(row[i]) as Item;
      moved = Math.max(moved, Math.abs(item.x - x));
      item.x = x;
    });
    return moved;
  };
  // A step only leaves its place for what hangs below it when that is a fan or a join: a plain run (one step leading to one
  // step that has no other way in) stays on one vertical line however lopsided the branches further down are.
  const pulledByChildren = (i: Item) => (i.down.length === 1 && (items.get(i.down[0]) as Item).up.length === 1 ? [] : i.down);
  // Down, then up: each row moves toward what it hangs from, then toward what hangs from it, until it settles.
  for (let pass = 0; pass < MAX_PASSES; pass++) {
    let moved = 0;
    for (let l = 1; l < layers.length; l++) moved = Math.max(moved, settle(l, (i) => i.up));
    for (let l = layers.length - 2; l >= 0; l--) moved = Math.max(moved, settle(l, pulledByChildren));
    if (moved < 0.25) break;
  }
  for (let l = 1; l < layers.length; l++) settle(l, (i) => i.up);

  // The first step stays where the flow starts so the picture does not drift sideways.
  const first = ids[0] ? (items.get(ids[0]) as Item).x : 0;
  const positions: Record<string, { x: number; y: number }> = {};
  for (const id of ids) {
    const item = items.get(id) as Item;
    positions[id] = { x: Math.round(item.x - first + ORIGIN_X), y: ORIGIN_Y + item.layer * ROW_GAP };
  }
  return positions;
}
