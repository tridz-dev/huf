/**
 * Add a step from the keyboard (Cmd+K palette): behind the selected step, or at the end of the flow. Same graph rules as the
 * "Add step" cards on the canvas; what used to follow the chosen spot moves down one row so the new card never sits on it.
 */
import { addActionStep, computeOpenEnds } from '../flow-graph/flowCanvasGraph';
import { subtreeIds } from '../flow/flowEdgeLabels';
import { ROW_GAP } from '../flow/flowLayout';
import { edgeRoute } from '../../services/flowSerializer';
import { branchHandlesFor } from '../flow/flowBranches';
import type { ActionConfig, FlowEdgeRoute } from '../../types/flow.types';
import type { Graph } from './cloneSteps';

export interface InsertSpot {
  sourceId: string;
  route: FlowEdgeRoute;
}

type Cfg = ({ type?: string } & Record<string, unknown>) | undefined;

/**
 * Where a new step goes: behind the selected step (its first free exit, else its first exit), or at the last open end of the
 * flow. `null` when there is nowhere to attach one (no trigger yet, or only a finished path).
 */
export function insertSpot(graph: Graph, selectedId: string | null): InsertSpot | null {
  const ends = computeOpenEnds(graph.nodes, graph.edges);
  const selected = selectedId ? graph.nodes.find((n) => n.id === selectedId) : undefined;
  if (selected && selected.data.nodeType !== 'end') {
    const free = ends.find((o) => o.nodeId === selected.id);
    if (free) return { sourceId: selected.id, route: free.route };
    const cfg = selected.data.actionConfig as Cfg;
    if (cfg?.type === 'router') return { sourceId: selected.id, route: 'option' };
    const first = branchHandlesFor(cfg?.type, cfg)[0];
    return { sourceId: selected.id, route: first?.route ?? 'next' };
  }
  const last = ends.filter((o) => !o.optional).pop() ?? ends[ends.length - 1];
  return last ? { sourceId: last.nodeId, route: last.route } : null;
}

export interface InsertResult extends Graph {
  newId: string;
}

export function insertStep(graph: Graph, spot: InsertSpot, actionId: string, config: ActionConfig): InsertResult | 'end-in-front' | null {
  const displaced = graph.edges.filter((e) => e.source === spot.sourceId && edgeRoute(e) === spot.route).map((e) => e.target);
  const added = addActionStep(graph.nodes, graph.edges, spot.sourceId, spot.route, actionId, config);
  if (!added || added === 'end-in-front') return added;
  const newNode = added.nodes[added.nodes.length - 1];
  const moving = new Set<string>();
  for (const target of displaced) for (const id of subtreeIds(target, added.edges)) if (id !== newNode.id) moving.add(id);
  const nodes = added.nodes.map((n) => (moving.has(n.id) ? { ...n, position: { x: n.position.x, y: n.position.y + ROW_GAP } } : { ...n, selected: n.id === newNode.id }));
  return { nodes, edges: added.edges, newId: newNode.id };
}
