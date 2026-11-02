/**
 * Pure graph edits for the Flow canvas: removing a step (with or without its followers), checking a new
 * connection, and finding steps nothing leads to. Edge routing fields (on_true, options, approve_next...)
 * are derived from edges on save (see flowSerializer), so editing edges here is all it takes to keep them right.
 */
import type { FlowEdge, FlowEdgeRoute, FlowNode } from '../../types/flow.types';
import { edgeRoute, makeFlowEdge } from '../../services/flowSerializer';
import { branchHandlesFor } from './flowBranches';
import { subtreeIds } from './flowEdgeLabels';

export type RemoveStepMode = 'reconnect' | 'cascade';

export interface FlowGraphLike {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

/** How many edges leave a step: decides whether "remove and reconnect" has a single successor to join. */
export function outgoingEdges(edges: FlowEdge[], nodeId: string): FlowEdge[] {
  return edges.filter((e) => e.source === nodeId);
}

/**
 * Remove a step.
 * - `reconnect`: the step goes; when it had exactly one way forward, every step that led into it now leads to that
 *   follower on the same route (router path names are kept). A step with several branches cannot be bridged, so its
 *   branches are simply left unconnected.
 * - `cascade`: the step goes together with every step that can only be reached through it. A step that something
 *   else still leads to stays.
 */
export function removeStep(graph: FlowGraphLike, nodeId: string, mode: RemoveStepMode): FlowGraphLike {
  const { nodes, edges } = graph;
  if (mode === 'cascade') {
    const subtree = subtreeIds(nodeId, edges);
    const keep = new Set<string>();
    const stack: string[] = nodes.filter((n) => !subtree.has(n.id)).map((n) => n.id);
    while (stack.length) {
      const cur = stack.pop() as string;
      for (const e of edges) {
        if (e.source === cur && subtree.has(e.target) && e.target !== nodeId && !keep.has(e.target)) {
          keep.add(e.target);
          stack.push(e.target);
        }
      }
    }
    const gone = new Set([...subtree].filter((id) => id === nodeId || !keep.has(id)));
    return {
      nodes: nodes.filter((n) => !gone.has(n.id)),
      edges: edges.filter((e) => !gone.has(e.source) && !gone.has(e.target)),
    };
  }

  const incoming = edges.filter((e) => e.target === nodeId);
  const outgoing = outgoingEdges(edges, nodeId);
  const rest = edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
  let nextNodes = nodes.filter((n) => n.id !== nodeId);
  if (outgoing.length !== 1 || incoming.length === 0) return { nodes: nextNodes, edges: rest };

  const follower = outgoing[0].target;
  const bridged = [...rest];
  for (const inc of incoming) {
    if (inc.source === follower) continue;
    const route = edgeRoute(inc);
    if (bridged.some((e) => e.source === inc.source && e.target === follower && edgeRoute(e) === route)) continue;
    const index = bridged.filter((e) => e.source === inc.source && edgeRoute(e) === route).length;
    bridged.push(makeFlowEdge(inc.source, follower, route, { label: typeof inc.label === 'string' ? inc.label : undefined, index }));
  }
  // A router whose "nothing matches" path was the removed step falls back to its follower.
  nextNodes = nextNodes.map((n) => {
    const cfg = n.data.actionConfig as ({ type?: string; default?: unknown } & Record<string, unknown>) | undefined;
    return cfg?.type === 'router' && cfg.default === nodeId ? { ...n, data: { ...n.data, actionConfig: { ...cfg, default: follower } as never } } : n;
  });
  return { nodes: nextNodes, edges: bridged };
}

/** Steps that cannot be reached from any trigger. Empty when the flow has no trigger yet (nothing to measure against). */
export function unreachableNodeIds(nodes: Array<Pick<FlowNode, 'id' | 'data'>>, edges: Array<Pick<FlowEdge, 'source' | 'target'>>): Set<string> {
  const roots = nodes.filter((n) => n.data.nodeType === 'trigger').map((n) => n.id);
  if (roots.length === 0) return new Set();
  const reached = new Set<string>(roots);
  const queue = [...roots];
  while (queue.length) {
    const from = queue.pop() as string;
    for (const e of edges) {
      if (e.source === from && !reached.has(e.target)) {
        reached.add(e.target);
        queue.push(e.target);
      }
    }
  }
  return new Set(nodes.filter((n) => !reached.has(n.id)).map((n) => n.id));
}

export interface ConnectionRequest {
  source: string;
  target: string;
  route: FlowEdgeRoute;
}

/** Routes a step can start a connection from. */
function allowedRoutes(node: FlowNode): FlowEdgeRoute[] {
  if (node.data.nodeType === 'end') return [];
  if (node.data.nodeType === 'trigger') return ['next'];
  const cfg = node.data.actionConfig as ({ type?: string } & Record<string, unknown>) | undefined;
  if (cfg?.type === 'router') return ['option'];
  const handles = branchHandlesFor(cfg?.type, cfg);
  return handles.length > 0 ? handles.map((h) => h.route) : ['next'];
}

/** Plain-language reason a new connection is refused, or null when it is fine. */
export function connectionProblem(graph: FlowGraphLike, req: ConnectionRequest): string | null {
  const source = graph.nodes.find((n) => n.id === req.source);
  const target = graph.nodes.find((n) => n.id === req.target);
  if (!source || !target) return "That step doesn't exist any more.";
  if (source.id === target.id) return "A step can't connect to itself.";
  if (target.data.nodeType === 'trigger') return "Nothing can lead into the trigger. Connect from the trigger to a step instead.";
  if (source.data.nodeType === 'end') return "A step that ends the flow can't lead to another step.";
  if (!allowedRoutes(source).includes(req.route)) return "That connection point can't start a connection on this step.";
  if (graph.edges.some((e) => e.source === req.source && e.target === req.target && edgeRoute(e) === req.route)) {
    return 'These two steps are already connected.';
  }
  if (subtreeIds(req.target, graph.edges).has(req.source)) {
    return "That would send the flow back to an earlier step. Flows only run forward; use a loop step to repeat work.";
  }
  return null;
}
