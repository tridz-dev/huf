/**
 * Copying steps inside a flow or between flows: fresh ids, the connections between the copied steps kept, every reference
 * to a copied step pointed at its copy. Pure; Duplicate (same flow) and Paste (maybe another flow) both build on it.
 */
import { edgeRoute, makeFlowEdgeId } from '../../services/flowSerializer';
import type { FlowEdge, FlowNode } from '../../types/flow.types';

export interface Graph {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

/** An id no step uses yet, in the editor's own `node_<time>` style. Node ids may only hold letters, digits and "_" (max 64). */
export function uniqueNodeId(taken: Set<string>, now: number): string {
  let id = `node_${now}`;
  for (let n = 2; taken.has(id); n++) id = `node_${now}_${n}`;
  taken.add(id);
  return id;
}

/** "Send email" -> "Send email (copy)"; copying that again -> "Send email (copy 2)". Never a title another step already has. */
export function copyLabel(label: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  const base = label.replace(/ \(copy( \d+)?\)$/, '');
  let candidate = `${base} (copy)`;
  for (let n = 2; used.has(candidate); n++) candidate = `${base} (copy ${n})`;
  return candidate;
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Replace every whole-word use of an old step id inside any string of `value` (references, expressions, templates). */
export function remapIds<T>(value: T, map: Map<string, string>): T {
  if (map.size === 0) return value;
  const ids = [...map.keys()].sort((a, b) => b.length - a.length).map(escapeRe);
  const re = new RegExp(`(?<![A-Za-z0-9_])(${ids.join('|')})(?![A-Za-z0-9_])`, 'g');
  const walk = (v: unknown): unknown => {
    if (typeof v === 'string') return v.replace(re, (m) => map.get(m) ?? m);
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v as Record<string, unknown>).map(([k, x]) => [k, walk(x)]));
    return v;
  };
  return walk(value) as T;
}

export interface CloneOptions {
  now: number;
  /** Where each copy goes, from the original's position. */
  place: (node: FlowNode) => { x: number; y: number };
  /** Extra per-step changes (strip secrets, new title). Runs on a deep copy that already has its new id. */
  adjust?: (copy: FlowNode, original: FlowNode) => FlowNode;
  /** Titles already in use; copies get "(copy)" titles unless `keepTitles` (then only a title that clashes gets one). */
  takenLabels?: Iterable<string>;
  keepTitles?: boolean;
}

export interface CloneResult {
  nodes: FlowNode[];
  edges: FlowEdge[];
  /** old id -> new id */
  idMap: Map<string, string>;
}

const deepCopy = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/**
 * Deep copies of the steps `ids` of `source`, with new ids chosen so they collide with nothing in `takenIds`, and copies of the
 * connections that run between two copied steps. Connections to steps that were not copied are left out.
 */
export function cloneSteps(source: Graph, ids: string[], takenIds: Iterable<string>, opts: CloneOptions): CloneResult {
  const wanted = new Set(ids);
  const originals = source.nodes.filter((n) => wanted.has(n.id));
  const taken = new Set(takenIds);
  const idMap = new Map<string, string>();
  for (const n of originals) idMap.set(n.id, uniqueNodeId(taken, opts.now));
  const labels = new Set(opts.takenLabels ?? []);

  const nodes = originals.map((original) => {
    const copy = deepCopy(original);
    const position = opts.place(original);
    const oldLabel = original.data.label;
    const label = opts.keepTitles && !labels.has(oldLabel) ? oldLabel : copyLabel(oldLabel, labels);
    labels.add(label);
    let out: FlowNode = {
      ...copy,
      id: idMap.get(original.id) as string,
      selected: false,
      dragging: false,
      position,
      data: { ...remapIds(copy.data, idMap), label, status: undefined },
    };
    delete (out as { positionAbsolute?: unknown }).positionAbsolute;
    // A router's "nothing matches" fallback names a step; if that step was not copied there is nothing to fall back to.
    const cfg = out.data.actionConfig as ({ type?: string; default?: unknown } & Record<string, unknown>) | undefined;
    const originalDefault = (original.data.actionConfig as { default?: unknown } | undefined)?.default;
    if (cfg?.type === 'router' && typeof originalDefault === 'string' && !idMap.has(originalDefault)) {
      out = { ...out, data: { ...out.data, actionConfig: { ...cfg, default: undefined } as never } };
    }
    return opts.adjust ? opts.adjust(out, original) : out;
  });

  const edges = source.edges
    .filter((e) => wanted.has(e.source) && wanted.has(e.target))
    .map((e) => {
      const source2 = idMap.get(e.source) as string;
      const target2 = idMap.get(e.target) as string;
      const route = edgeRoute(e);
      const index = Number(/#(\d+)->/.exec(e.id)?.[1]);
      const oldTargetLabel = source.nodes.find((n) => n.id === e.target)?.data.label;
      const newTarget = nodes.find((n) => n.id === target2);
      const edge: FlowEdge = { ...deepCopy(e), id: makeFlowEdgeId(source2, route, target2, Number.isFinite(index) ? index : undefined), source: source2, target: target2, selected: false };
      // A router path that was named after its step follows the copy's new title.
      if (route === 'option' && edge.label === oldTargetLabel && newTarget) edge.label = newTarget.data.label;
      return edge;
    });
  return { nodes, edges, idMap };
}

/** What a step takes on the canvas when its real size is not known yet (width of a card, a tall card's height). */
const BOX = { width: 236, height: 110 };
/** Space (px) kept between a copy and any other step. */
const CLEAR = 16;
const NUDGE = 24;
/** One column over: a card and the gap beside it. */
const COLUMN = 284;

/**
 * Moves copies off the steps they would land on, so a duplicate or a paste never sits on top of a card: first a little further
 * down (up to 3 steps of 24px), otherwise one column to the right (then two), otherwise further down up to 288px, keeping the
 * copies' places relative to each other. The first move that clears every step wins. When nothing clears the copies stay as placed.
 */
export function clearOfSteps(copies: FlowNode[], others: FlowNode[]): FlowNode[] {
  const box = (n: FlowNode) => ({ x: n.position.x, y: n.position.y, w: n.width ?? BOX.width, h: n.height ?? BOX.height });
  const hits = (dx: number, dy: number) => copies.some((c) => {
    const a = box(c);
    return others.some((o) => {
      const b = box(o);
      return a.x + dx < b.x + b.w + CLEAR && a.x + dx + a.w + CLEAR > b.x && a.y + dy < b.y + b.h + CLEAR && a.y + dy + a.h + CLEAR > b.y;
    });
  });
  if (!hits(0, 0)) return copies;
  // Order of preference: a short nudge down (3 steps), then one column right (then two), then further down up to 12 steps.
  const tries: Array<{ dx: number; dy: number }> = [];
  for (let dy = 0; dy <= 3 * NUDGE; dy += NUDGE) tries.push({ dx: 0, dy });
  for (const dx of [COLUMN, 2 * COLUMN]) for (let dy = 0; dy <= 3 * NUDGE; dy += NUDGE) tries.push({ dx, dy });
  for (let dy = 4 * NUDGE; dy <= 12 * NUDGE; dy += NUDGE) tries.push({ dx: 0, dy });
  const best = tries.find((t) => !hits(t.dx, t.dy));
  if (!best) return copies;
  return copies.map((c) => ({ ...c, position: { x: c.position.x + best.dx, y: c.position.y + best.dy } }));
}
