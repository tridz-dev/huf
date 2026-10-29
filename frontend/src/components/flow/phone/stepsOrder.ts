import type { Edge, Node } from 'reactflow';
import type { FlowNodeData } from '@/types/flow.types';

export interface OrderedStep {
  id: string;
  /** How many paths deep this step is (0 = the main path). */
  depth: number;
  /** The branch this step starts, in words ("Yes", "No", "Approved"), when it is the first step of one. */
  branch: string | null;
}

const ROUTE_WORDS: Record<string, string> = {
  true: 'Yes', false: 'No', approved: 'Approved', rejected: 'Rejected', timeout: 'Timed out', loop: 'For each item', done: 'When done',
  yes: 'Yes', no: 'No',
};

function branchWord(edge: Edge): string | null {
  const data = edge.data as { route?: string; label?: string } | undefined;
  const label = typeof edge.label === 'string' ? edge.label : data?.label;
  if (label) return label;
  const route = data?.route;
  if (!route || route === 'next') return null;
  return ROUTE_WORDS[route] ?? route;
}

/**
 * The steps of a flow in reading order for a list: the trigger first, then each step after the one that leads to it; at a
 * split the branches follow one after the other, each starting with its name. Steps nothing leads to come last. Pure.
 */
export function orderSteps(nodes: Node<FlowNodeData>[], edges: Edge[]): OrderedStep[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const out = new Map<string, Edge[]>();
  for (const e of edges) {
    if (!byId.has(e.source) || !byId.has(e.target)) continue;
    out.set(e.source, [...(out.get(e.source) ?? []), e]);
  }
  const seen = new Set<string>();
  const result: OrderedStep[] = [];
  const visit = (id: string, depth: number, branch: string | null) => {
    if (seen.has(id)) return;
    seen.add(id);
    result.push({ id, depth, branch });
    const next = out.get(id) ?? [];
    const split = next.length > 1;
    for (const e of next) visit(e.target, split ? depth + 1 : depth, split ? branchWord(e) : null);
  };
  const triggers = nodes.filter((n) => n.data.nodeType === 'trigger');
  const entries = triggers.length > 0 ? triggers : nodes.filter((n) => !edges.some((e) => e.target === n.id)).slice(0, 1);
  for (const t of entries) visit(t.id, 0, null);
  for (const n of nodes) if (!seen.has(n.id)) visit(n.id, 0, null);
  return result;
}
