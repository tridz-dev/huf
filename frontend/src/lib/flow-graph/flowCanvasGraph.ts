import type { Connection, Edge, Node } from 'reactflow';
import { branchHandlesFor } from '../flow/flowBranches';
import { branchColumnShift, subtreeIds } from '../flow/flowEdgeLabels';
import { actionLabel } from '../flow/flowLabels';
import { COLUMN_GAP } from '../flow/flowLayout';
import { unreachableNodeIds } from '../flow/flowEdit';
import { makeFlowEdge, edgeRoute } from '../../services/flowSerializer';
import { actionOptions } from '../../data/actions';
import type { ActionConfig, FlowEdgeRoute, FlowNodeData } from '../../types/flow.types';

/** Ids of cards and lines that exist only on screen; they are never written back to the flow. */
export const RENDER_ONLY_NODE_PREFIX = 'ghost-';
export const RENDER_ONLY_EDGE_PREFIX = 'edge-ghost-';

type StepCfg = ({ type?: string } & Record<string, unknown>) | undefined;

/** A spot in the graph that still needs a successor: the step and the route that leaves nowhere. */
export interface OpenEnd {
  nodeId: string;
  route: FlowEdgeRoute;
  handleId?: string;
  label?: string;
  position: { x: number; y: number };
  offset: number;
  /** The branch may stay unconnected ("When done", "Timed out"). */
  optional?: boolean;
}

/**
 * Open ends of the graph: every (node, route) that still needs a successor. A plain step has one open
 * end (its 'next'); branching steps have one per missing branch.
 */
export function computeOpenEnds(nodes: Node<FlowNodeData>[], edges: Edge[]): OpenEnd[] {
  const ends: OpenEnd[] = [];
  for (const n of nodes) {
    if (n.data.nodeType === 'end') continue;
    const out = edges.filter((e) => e.source === n.id);
    const cfg = n.data.actionConfig as StepCfg;
    if (cfg?.type === 'router') {
      if (!out.some((e) => edgeRoute(e) === 'option')) ends.push({ nodeId: n.id, route: 'option', handleId: 'option', label: 'Path', position: n.position, offset: 0 });
      continue;
    }
    const handles = branchHandlesFor(cfg?.type, cfg);
    if (handles.length === 0) {
      if (!out.some((e) => edgeRoute(e) === 'next')) ends.push({ nodeId: n.id, route: 'next', position: n.position, offset: 0 });
      continue;
    }
    handles.forEach((h, i) => {
      if (!out.some((e) => edgeRoute(e) === h.route)) {
        ends.push({ nodeId: n.id, route: h.route, handleId: h.handleId, label: h.label, position: n.position, offset: (i - (handles.length - 1) / 2) * COLUMN_GAP, optional: h.optional });
      }
    });
  }
  return ends;
}

/**
 * The steps of every loop's body: each step reachable from the loop's "For each item" connection, keyed by loop id.
 * The body ends where its chain has nothing after it; the run then goes back to the loop for the next item.
 */
export function loopBodies(nodes: Node<FlowNodeData>[], edges: Edge[]): Map<string, Set<string>> {
  const bodies = new Map<string, Set<string>>();
  for (const loop of nodes) {
    if ((loop.data.actionConfig as StepCfg)?.type !== 'foreach') continue;
    const seen = new Set<string>();
    const stack = edges.filter((e) => e.source === loop.id && edgeRoute(e) === 'body').map((e) => e.target);
    while (stack.length) {
      const id = stack.pop() as string;
      if (seen.has(id) || id === loop.id) continue;
      seen.add(id);
      for (const e of edges) if (e.source === id) stack.push(e.target);
    }
    bodies.set(loop.id, seen);
  }
  return bodies;
}

/** A loop body's last step and the loop it returns to (drawn as a "Next item" line instead of an "Add step" card). */
export interface LoopBack {
  leafId: string;
  loopId: string;
}

export function loopBacks(nodes: Node<FlowNodeData>[], edges: Edge[], openEnds: OpenEnd[]): LoopBack[] {
  const bodies = loopBodies(nodes, edges);
  const out: LoopBack[] = [];
  for (const end of openEnds) {
    if (end.route !== 'next') continue;
    for (const [loopId, members] of bodies) if (members.has(end.nodeId)) { out.push({ leafId: end.nodeId, loopId }); break; }
  }
  return out;
}

export interface GhostSpot {
  end: OpenEnd;
  x: number;
  y: number;
}

/**
 * Where "Add step" cards go. Not drawn: a loop body's last step (it returns to the loop instead), an optional branch
 * ("When done", "Timed out") until its step is selected, and a spot where another step already sits (a step left
 * unconnected below): a card there would look like a stray box. Cards of one step are a full column apart.
 */
export function ghostSpots(nodes: Node<FlowNodeData>[], openEnds: OpenEnd[], edges: Edge[], selectedId: string | null): GhostSpot[] {
  const back = new Set(loopBacks(nodes, edges, openEnds).map((l) => l.leafId));
  const real = nodes.map((n) => n.position);
  const placed: Array<{ x: number; y: number }> = [];
  const out: GhostSpot[] = [];
  for (const end of openEnds) {
    if (end.route === 'next' && back.has(end.nodeId)) continue;
    if (end.optional && end.nodeId !== selectedId) continue;
    let x = end.position.x + end.offset;
    const y = end.position.y + 150;
    if (real.some((p) => Math.abs(p.x - x) < 230 && Math.abs(p.y - y) < 80)) continue;
    const dir = end.offset < 0 ? -1 : 1;
    let guard = 0;
    while (placed.some((p) => Math.abs(p.x - x) < 250 && Math.abs(p.y - y) < 80) && guard++ < 8) x += dir * COLUMN_GAP;
    placed.push({ x, y });
    out.push({ end, x, y });
  }
  return out;
}

/** Plain name of a branch for its pill on the connection; null when the connection needs none (a plain "next"). */
export function branchPillText(edge: Edge, source: Node<FlowNodeData> | undefined): string | null {
  const route = edgeRoute(edge);
  if (route === 'option') return (typeof edge.label === 'string' && edge.label) || 'Path';
  if (route === 'error') return 'If it fails';
  if (route === 'default') return 'Otherwise';
  const cfg = source?.data.actionConfig as StepCfg;
  return branchHandlesFor(cfg?.type, cfg).find((h) => h.route === route)?.label ?? null;
}

/**
 * Subtitle for End steps that have none: which path they close ("After “Approved”"), so Ends after different
 * branches can be told apart. Display only; never written to the flow.
 */
export function endSubtitles(nodes: Node<FlowNodeData>[], edges: Edge[]): Map<string, string> {
  const out = new Map<string, string>();
  for (const n of nodes) {
    if (n.data.nodeType !== 'end' || n.data.description) continue;
    const names = [...new Set(edges.filter((e) => e.target === n.id).map((e) => {
      const source = nodes.find((s) => s.id === e.source);
      return branchPillText(e, source) ?? source?.data.label ?? '';
    }).filter(Boolean))];
    if (names.length > 0) out.set(n.id, `After \u201c${names.slice(0, 2).join(', ')}\u201d${names.length > 2 ? '...' : ''}`);
  }
  return out;
}

/**
 * Why a step is flagged as cut off, or null when the trigger reaches it. "Nothing leads to this step" only fits a step with
 * no line into it; a step that has one, but from a part that is itself cut off, is "Not connected to the trigger".
 */
export function orphanNote(id: string, nodes: Array<Pick<Node<FlowNodeData>, 'id' | 'data'>>, edges: Array<Pick<Edge, 'source' | 'target'>>): string | null {
  if (!unreachableNodeIds(nodes, edges).has(id)) return null;
  return edges.some((e) => e.target === id && e.source !== id) ? 'Not connected to the trigger' : 'Nothing leads to this step';
}

/** Edges and moved steps after connecting `source` to `target` on `route`. */
export function connectSteps(
  nodes: Node<FlowNodeData>[],
  edges: Edge[],
  source: string,
  target: string,
  route: FlowEdgeRoute,
): { newEdges: Edge[]; updatedNodes?: Node<FlowNodeData>[] } {
  const targetLabel = nodes.find((n) => n.id === target)?.data.label;
  // Single-target routes (next/true/false/approve/...) replace an existing edge on the same handle.
  const multi = route === 'option' || route === 'body';
  const kept = multi ? edges : edges.filter((e) => !(e.source === source && edgeRoute(e) === route));
  const index = kept.filter((e) => e.source === source && edgeRoute(e) === route).length;
  const newEdges = [...kept, makeFlowEdge(source, target, route, { label: targetLabel, index })];

  // Give each branch of a step its own column so a new path is never hidden behind another box.
  const targetNode = nodes.find((n) => n.id === target);
  const siblings = kept.filter((e) => e.source === source && e.target !== target).map((e) => nodes.find((n) => n.id === e.target)?.position.x);
  const shift = targetNode && siblings.length > 0
    ? branchColumnShift(targetNode.position.x, siblings.filter((x): x is number => typeof x === 'number'))
    : 0;
  let updatedNodes: Node<FlowNodeData>[] | undefined;
  if (shift !== 0) {
    const moving = subtreeIds(target, newEdges);
    updatedNodes = nodes.map((n) => (moving.has(n.id) ? { ...n, position: { ...n.position, x: n.position.x + shift } } : n));
  }
  return { newEdges, updatedNodes };
}

/**
 * The graph after adding an action step (or End) behind `sourceId` on `sourceRoute`; edges that left the source
 * on that route move onto the new step. `null` when End would be put in front of another step.
 */
export function addActionStep(
  nodes: Node<FlowNodeData>[],
  edges: Edge[],
  sourceId: string,
  sourceRoute: FlowEdgeRoute,
  actionId: string,
  config: ActionConfig,
): { nodes: Node<FlowNodeData>[]; edges: Edge[] } | 'end-in-front' | null {
  const sourceNode = nodes.find((n) => n.id === sourceId);
  if (!sourceNode) return null;

  const newNodeId = `node_${Date.now()}`;
  const option = actionOptions.find((a) => a.id === actionId);
  const isEnd = actionId === 'end';
  // Fan branch targets out sideways (True/False, approve/reject, router paths) so they never stack on one spot.
  const sourceCfg = sourceNode.data.actionConfig as StepCfg;
  const sourceHandles = branchHandlesFor(sourceCfg?.type, sourceCfg);
  const routeIndex = sourceHandles.findIndex((h) => h.route === sourceRoute);
  const sideOffset = sourceHandles.length > 0 && routeIndex >= 0
    ? (routeIndex - (sourceHandles.length - 1) / 2) * COLUMN_GAP
    : sourceCfg?.type === 'router'
      ? edges.filter((e) => e.source === sourceId && edgeRoute(e) === 'option').length * COLUMN_GAP
      : 0;
  const newNode: Node<FlowNodeData> = {
    id: newNodeId,
    type: isEnd ? 'end' : 'action',
    position: { x: sourceNode.position.x + sideOffset, y: sourceNode.position.y + 150 },
    data: isEnd
      ? { label: actionLabel(actionId), nodeType: 'end', icon: option?.icon || 'CheckCircle2', configured: true, endConfig: {} }
      : {
        // The palette card name is the node title and the sidebar title.
        label: actionLabel(actionId),
        nodeType: 'action',
        icon: option?.icon || 'Play',
        configured: false,
        actionConfig: config
      }
  };

  // Edges that left the source on the same route move onto the new node (insertion mid-chain).
  const moving = edges.filter((e) => e.source === sourceId && edgeRoute(e) === sourceRoute);
  if (isEnd && moving.length > 0) return 'end-in-front';
  const rest = edges.filter((e) => !moving.includes(e));
  const firstHandle = branchHandlesFor((config as { type?: string }).type)[0];
  const movedRoute: FlowEdgeRoute =
    (config as { type?: string }).type === 'router' ? 'option'
      : (config as { type?: string }).type === 'foreach' ? 'next'
        : firstHandle?.route ?? 'next';

  const newEdges = [
    ...rest,
    makeFlowEdge(sourceId, newNodeId, sourceRoute, { label: newNode.data.label, index: rest.filter((e) => e.source === sourceId && edgeRoute(e) === sourceRoute).length }),
    ...moving.map((e, i) => makeFlowEdge(newNodeId, e.target, movedRoute, { label: nodes.find((n) => n.id === e.target)?.data.label, index: i })),
  ];
  return { nodes: [...nodes, newNode], edges: newEdges };
}

/** Connection handle -> route (`next` when the handle has no name). */
export const connectionRoute = (connection: Connection): FlowEdgeRoute =>
  (connection.sourceHandle as FlowEdgeRoute | null) ?? 'next';
