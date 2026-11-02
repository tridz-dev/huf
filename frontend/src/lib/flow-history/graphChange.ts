/**
 * What changed between two versions of a flow's steps and connections, in plain words, and which edits belong to the
 * same undo step. Pure: the editor's undo history uses it to decide whether a write is a real edit (a move, a typed
 * letter, a new connection) or only view state (which step is selected, how big a card was measured) and to name it.
 */
import type { FlowEdge, FlowNode } from '../../types/flow.types';

export interface GraphSnapshot {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export type ChangeKind = 'add' | 'remove' | 'connect' | 'disconnect' | 'reconnect' | 'move' | 'edit' | 'layout';

export interface GraphChange {
  kind: ChangeKind;
  /** Plain-language name shown in tooltips and announcements: "Moved a step". */
  label: string;
  /** Edits with the same group key made close together become one undo step (typing, dragging). */
  group?: string;
}

/** Per-node view state that is not part of the flow: selection, measured size, drag flag, live run status. */
const VIEW_ONLY_NODE_KEYS = new Set(['selected', 'dragging', 'width', 'height', 'positionAbsolute', 'resizing', 'measured']);
const VIEW_ONLY_EDGE_KEYS = new Set(['selected', 'markerEnd', 'animated', 'style']);

const stable = (value: unknown): string =>
  JSON.stringify(value, (_key, v) => {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      return Object.keys(v as Record<string, unknown>).sort().reduce<Record<string, unknown>>((acc, k) => {
        acc[k] = (v as Record<string, unknown>)[k];
        return acc;
      }, {});
    }
    return v;
  });

const nodeCache = new WeakMap<object, { content: string; position: string }>();
const edgeCache = new WeakMap<object, string>();

/** The parts of a step that make up the flow, split into what it is and where it sits. */
function nodeParts(node: FlowNode): { content: string; position: string } {
  const hit = nodeCache.get(node);
  if (hit) return hit;
  const rest: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(node)) {
    if (k === 'position' || VIEW_ONLY_NODE_KEYS.has(k)) continue;
    rest[k] = v;
  }
  // Live run status comes from the server, not from the author.
  const data = { ...((node.data ?? {}) as unknown as Record<string, unknown>) };
  delete data.status;
  rest.data = data;
  const parts = {
    content: stable(rest),
    position: `${Math.round(node.position?.x ?? 0)},${Math.round(node.position?.y ?? 0)}`,
  };
  nodeCache.set(node, parts);
  return parts;
}

function edgeContent(edge: FlowEdge): string {
  const hit = edgeCache.get(edge);
  if (hit !== undefined) return hit;
  const rest: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(edge)) if (!VIEW_ONLY_EDGE_KEYS.has(k)) rest[k] = v;
  const out = stable(rest);
  edgeCache.set(edge, out);
  return out;
}

const titleOf = (node: FlowNode | undefined): string => {
  const label = (node?.data as { label?: string } | undefined)?.label?.trim();
  return label ? `“${label}”` : 'a step';
};

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** How long (ms) a pause may be before the next edit of the same group becomes a new undo step. */
export const GROUP_WINDOW_MS: Record<string, number> = { edit: 1200, move: 700 };

/** True when the two graphs are the same flow (ignoring selection, measured sizes and live status). */
export function sameGraph(a: GraphSnapshot, b: GraphSnapshot): boolean {
  return describeChange(a, b) === null;
}

/**
 * The change from `before` to `after`, or `null` when nothing the author did differs (selection, measured card sizes and
 * live status do not count). `hint` lets a caller that knows better (Tidy layout) name the change.
 */
export function describeChange(before: GraphSnapshot, after: GraphSnapshot, hint?: Partial<GraphChange>): GraphChange | null {
  const beforeNodes = new Map(before.nodes.map((n) => [n.id, n]));
  const afterNodes = new Map(after.nodes.map((n) => [n.id, n]));
  const added = after.nodes.filter((n) => !beforeNodes.has(n.id));
  const removed = before.nodes.filter((n) => !afterNodes.has(n.id));

  const beforeEdges = new Map(before.edges.map((e) => [e.id, e]));
  const afterEdges = new Map(after.edges.map((e) => [e.id, e]));
  const edgesAdded = after.edges.filter((e) => !beforeEdges.has(e.id)).length;
  const edgesRemoved = before.edges.filter((e) => !afterEdges.has(e.id)).length;
  const edgesChanged = after.edges.filter((e) => beforeEdges.has(e.id) && edgeContent(beforeEdges.get(e.id) as FlowEdge) !== edgeContent(e)).length;

  const moved: FlowNode[] = [];
  const edited: FlowNode[] = [];
  for (const n of after.nodes) {
    const old = beforeNodes.get(n.id);
    if (!old || old === n) continue;
    const a = nodeParts(old);
    const b = nodeParts(n);
    if (a.content !== b.content) edited.push(n);
    else if (a.position !== b.position) moved.push(n);
  }
  // A step edited and moved in the same write counts as an edit; the position rides along in the same undo step.
  const positionsChanged = after.nodes.some((n) => {
    const old = beforeNodes.get(n.id);
    return old && old !== n && nodeParts(old).position !== nodeParts(n).position;
  });

  let change: GraphChange | null = null;
  if (added.length > 0 || removed.length > 0) {
    if (added.length > 0 && removed.length === 0) {
      change = { kind: 'add', label: added.length === 1 ? `Added ${titleOf(added[0])}` : `Added ${added.length} steps` };
    } else if (removed.length > 0 && added.length === 0) {
      change = { kind: 'remove', label: removed.length === 1 ? `Deleted ${titleOf(removed[0])}` : `Deleted ${removed.length} steps` };
    } else {
      change = { kind: 'edit', label: 'Changed the flow' };
    }
  } else if (edgesAdded > 0 || edgesRemoved > 0) {
    if (edgesAdded > 0 && edgesRemoved === 0) change = { kind: 'connect', label: plural(edgesAdded, 'Connected two steps', 'Connected steps') };
    else if (edgesRemoved > 0 && edgesAdded === 0) change = { kind: 'disconnect', label: plural(edgesRemoved, 'Disconnected two steps', 'Disconnected steps') };
    else change = { kind: 'reconnect', label: 'Changed connections' };
  } else if (edited.length > 0) {
    const ids = edited.map((n) => n.id).sort();
    change = {
      kind: 'edit',
      label: edited.length === 1 ? `Edited ${titleOf(edited[0])}` : `Edited ${edited.length} steps`,
      group: `edit:${ids.join(',')}`,
    };
  } else if (edgesChanged > 0) {
    change = { kind: 'edit', label: 'Renamed a path', group: 'edit:edges' };
  } else if (moved.length > 0) {
    change = {
      kind: 'move',
      label: moved.length === 1 ? 'Moved a step' : `Moved ${moved.length} steps`,
      group: 'move',
    };
  } else if (positionsChanged) {
    change = { kind: 'move', label: 'Moved a step', group: 'move' };
  }

  if (!change) return null;
  return { ...change, ...(hint ?? {}) };
}
