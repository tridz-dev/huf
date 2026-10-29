import type { Connection, Edge, Node } from 'reactflow';
import { branchHandlesFor } from '../flow/flowBranches';
import { branchColumnShift, subtreeIds } from '../flow/flowEdgeLabels';
import { actionLabel } from '../flow/flowLabels';
import { makeFlowEdge, edgeRoute } from '../../services/flowSerializer';
import { actionOptions } from '../../data/actions';
import type { ActionConfig, FlowEdgeRoute, FlowNodeData } from '../../types/flow.types';

type StepCfg = ({ type?: string } & Record<string, unknown>) | undefined;

/** A spot in the graph that still needs a successor: the step and the route that leaves nowhere. */
export interface OpenEnd {
  nodeId: string;
  route: FlowEdgeRoute;
  handleId?: string;
  label?: string;
  position: { x: number; y: number };
  offset: number;
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
        ends.push({ nodeId: n.id, route: h.route, handleId: h.handleId, label: h.label, position: n.position, offset: (i - (handles.length - 1) / 2) * 240 });
      }
    });
  }
  return ends;
}

/**
 * Where each open end's "Add step" card sits. A leaf whose step below is not connected to it would draw its
 * card on top of that step: slide the card sideways until the spot is free.
 */
export function ghostPositions(nodes: Node<FlowNodeData>[], openEnds: OpenEnd[]): Array<{ x: number; y: number }> {
  const taken: Array<{ x: number; y: number }> = nodes.map((n) => n.position);
  return openEnds.map((end) => {
    let x = end.position.x + end.offset;
    const y = end.position.y + 150;
    let guard = 0;
    const dir = end.offset < 0 ? -1 : 1; // a left-hand branch slides left, any other slides right
    while (taken.some((p) => Math.abs(p.x - x) < 230 && Math.abs(p.y - y) < 80) && guard++ < 8) x += dir * 280;
    taken.push({ x, y });
    return { x, y };
  });
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
    ? (routeIndex - (sourceHandles.length - 1) / 2) * 240
    : sourceCfg?.type === 'router'
      ? edges.filter((e) => e.source === sourceId && edgeRoute(e) === 'option').length * 240
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
