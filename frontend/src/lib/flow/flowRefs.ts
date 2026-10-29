/**
 * Which data a step may reference ("Insert data" picker). A step can only read the trigger and the
 * results of steps that ALWAYS ran before it: a step is offered only when every path from a trigger to
 * the current step goes through it (the save-time validator rejects anything else). Later steps, side
 * branches and the step itself never appear.
 */
import { edgeRoute } from '../../services/flowSerializer';
import type { FlowEdge } from '../../types/flow.types';

export interface FlowRefEntry {
  /** Reference path written into `{"$from": ...}` / expressions / `{placeholders}`. */
  ref: string;
  /** Shown to the user. */
  label: string;
  /** Short snake_case name safe to use as a `{placeholder}` in a prompt or template. */
  name: string;
}

type NodeLite = { id: string; position?: { x: number; y: number }; data: { label?: string; nodeType?: string } };
type EdgeLite = Pick<FlowEdge, 'source' | 'target' | 'sourceHandle' | 'data'>;

export function toPlaceholder(label: string, fallback: string): string {
  const cleaned = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return /^[a-z_]/.test(cleaned) ? cleaned : fallback;
}

/** Ids of nodes that sit on EVERY path from a trigger to `nodeId` (excluding the node itself). */
export function guaranteedPredecessors(nodeId: string, nodes: NodeLite[], edges: EdgeLite[]): Set<string> {
  const out = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  for (const e of edges) {
    out.set(e.source, [...(out.get(e.source) ?? []), e.target]);
    incoming.set(e.target, [...(incoming.get(e.target) ?? []), e.source]);
  }
  // Plain ancestors first (everything that can reach nodeId).
  const ancestors = new Set<string>();
  const stack = [nodeId];
  while (stack.length) {
    const cur = stack.pop() as string;
    for (const p of incoming.get(cur) ?? []) {
      if (!ancestors.has(p) && p !== nodeId) {
        ancestors.add(p);
        stack.push(p);
      }
    }
  }
  const roots = nodes.filter((n) => n.data.nodeType === 'trigger').map((n) => n.id);
  const reachableWithout = (skip: string): boolean => {
    const seen = new Set<string>(roots.filter((r) => r !== skip));
    const queue = [...seen];
    while (queue.length) {
      const cur = queue.pop() as string;
      if (cur === nodeId) return true;
      for (const t of out.get(cur) ?? []) {
        if (t !== skip && !seen.has(t)) {
          seen.add(t);
          queue.push(t);
        }
      }
    }
    return false;
  };
  const result = new Set<string>();
  for (const a of ancestors) if (!reachableWithout(a)) result.add(a);
  return result;
}

/** Loop (foreach) nodes whose body chain contains `nodeId`. */
export function enclosingLoops(nodeId: string, nodes: NodeLite[], edges: EdgeLite[]): string[] {
  const loops: string[] = [];
  const incoming = new Map<string, EdgeLite[]>();
  for (const e of edges) incoming.set(e.target, [...(incoming.get(e.target) ?? []), e]);
  const seen = new Set<string>();
  const stack = [nodeId];
  while (stack.length) {
    const cur = stack.pop() as string;
    if (seen.has(cur)) continue;
    seen.add(cur);
    for (const e of incoming.get(cur) ?? []) {
      if (edgeRoute(e as FlowEdge) === 'body') loops.push(e.source);
      stack.push(e.source);
    }
  }
  return [...new Set(loops)].filter((id) => nodes.some((n) => n.id === id));
}

/** Nodes reachable from a loop's body head(s) by following plain successors: the loop body chain. */
export function loopBodyNodes(loopId: string, edges: EdgeLite[]): string[] {
  const body: string[] = [];
  const seen = new Set<string>();
  const stack = edges.filter((e) => e.source === loopId && edgeRoute(e as FlowEdge) === 'body').map((e) => e.target);
  while (stack.length) {
    const cur = stack.pop() as string;
    if (seen.has(cur)) continue;
    seen.add(cur);
    body.push(cur);
    for (const e of edges) if (e.source === cur) stack.push(e.target);
  }
  return body;
}

export type RefScope = 'ancestors' | 'loop-body';

/**
 * The picker list for a field of `nodeId`. `ancestors` (default): trigger + guaranteed predecessors (+ the
 * current loop item when inside a loop body). `loop-body`: the steps inside THIS loop plus the current item,
 * for a loop's "result to collect".
 */
export function availableReferences(
  nodeId: string | null | undefined,
  nodes: NodeLite[],
  edges: EdgeLite[],
  scope: RefScope = 'ancestors'
): FlowRefEntry[] {
  const list: FlowRefEntry[] = [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const nodeEntry = (id: string): FlowRefEntry | null => {
    const n = byId.get(id);
    if (!n || n.data.nodeType !== 'action') return null;
    return { ref: id, label: `Result of "${n.data.label ?? id}"`, name: toPlaceholder(n.data.label ?? id, id) };
  };
  const loopEntries: FlowRefEntry[] = [
    { ref: 'foreach.item', label: 'Current item (in this loop)', name: 'item' },
    { ref: 'foreach.index', label: 'Item number (in this loop)', name: 'index' },
  ];

  if (scope === 'loop-body') {
    if (!nodeId) return loopEntries;
    return [...loopEntries, ...loopBodyNodes(nodeId, edges).map(nodeEntry).filter((e): e is FlowRefEntry => Boolean(e))];
  }

  list.push({ ref: 'input', label: 'Trigger input', name: 'input' }, { ref: 'trigger', label: 'Trigger details', name: 'trigger' });
  if (!nodeId) return list;
  const guaranteed = guaranteedPredecessors(nodeId, nodes, edges);
  const loops = enclosingLoops(nodeId, nodes, edges);
  if (loops.length > 0) list.push(...loopEntries);
  // Keep canvas order (top to bottom) so the list reads like the flow.
  for (const n of [...nodes].sort((a, b) => (a.position?.y ?? 0) - (b.position?.y ?? 0))) {
    if (!guaranteed.has(n.id) || loops.includes(n.id)) continue;
    const entry = nodeEntry(n.id);
    if (entry) list.push(entry);
  }
  return list;
}

/** A placeholder name not already used in `taken`. */
export function uniqueName(base: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  if (!used.has(base)) return base;
  for (let i = 2; ; i++) if (!used.has(`${base}_${i}`)) return `${base}_${i}`;
}
