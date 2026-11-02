import { useMemo, useRef } from 'react';
import { MarkerType, type Edge, type Node } from 'reactflow';
import { branchHandlesFor, branchTone } from '@/lib/flow/flowBranches';
import { RENDER_ONLY_EDGE_PREFIX, RENDER_ONLY_NODE_PREFIX, branchPillText, endSubtitles, ghostSpots, loopBacks, type OpenEnd } from '@/lib/flow-graph/flowCanvasGraph';
import { edgeRoute } from '@/services/flowSerializer';
import type { FlowEdgeRoute, FlowNodeData } from '@/types/flow.types';
import type { AddStepGhostNodeData } from '../../nodes/AddStepGhostNode';
import type { InsertableEdgeData } from '../../edges/InsertableEdge';
import { withSelection } from './canvasView';
import { cardTitle, stepAriaLabel, stepOrder, useNodeFacts } from './nodeFacts';
import { CARD_STATUS_OF, type RunOverlay } from '@/lib/flow-graph/runOverlay';


const ARROW = { type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#8e8e99' } as const;
const ARROW_TAKEN = { ...ARROW, color: 'var(--good)' } as const;

type StepCfg = ({ type?: string } & Record<string, unknown>) | undefined;

/** The handle a connection leaves from: one per branch, so "When done" never shares the dot of "For each item". */
function handleFor(edge: Edge, source: Node<FlowNodeData> | undefined): string | undefined {
  const cfg = source?.data.actionConfig as StepCfg;
  if (cfg?.type === 'router') return 'option';
  const route = edgeRoute(edge);
  return branchHandlesFor(cfg?.type, cfg).find((h) => h.route === route)?.handleId ?? (edge.sourceHandle ?? undefined);
}

interface Params {
  canManage: boolean;
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  openEnds: OpenEnd[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectEdge: (edgeId: string) => void;
  onAddNode: (sourceNodeId: string, route?: FlowEdgeRoute) => void;
  onRemoveEdge: (edgeId: string) => void;
  /** A run opened on the canvas: its step colours, summaries and the connections it took. */
  overlay: RunOverlay | null;
  onDeleteNode: (nodeId: string) => void;
}

/**
 * What the canvas draws: the real steps and connections plus the on-screen-only extras (an "Add step" card per open
 * branch, a "Next item" line back to the loop from the end of its body, End subtitles naming the path they close).
 */
export function useRenderedGraph({ canManage, nodes, edges, openEnds, selectedNodeId, selectedEdgeId, onSelectEdge, onAddNode, onRemoveEdge, overlay, onDeleteNode }: Params) {
  const spots = useMemo(() => (canManage ? ghostSpots(nodes, openEnds, edges, selectedNodeId) : []), [canManage, nodes, openEnds, edges, selectedNodeId]);

  const ghostNodes = useMemo<Node<AddStepGhostNodeData>[]>(
    () =>
      spots.map(({ end, x, y }) => ({
        id: `${RENDER_ONLY_NODE_PREFIX}${end.nodeId}-${end.route}`,
        type: 'addStep',
        position: { x, y },
        draggable: false,
        selectable: false,
        connectable: false,
        focusable: false, // its own button is the control; the wrapper must not be a second, nested one
        data: { sourceNodeId: end.nodeId, route: end.route, branchLabel: end.label, onAddNode },
      })),
    [spots, onAddNode],
  );

  const ghostEdges = useMemo<Edge[]>(
    () =>
      spots.map(({ end }) => ({
        id: `${RENDER_ONLY_EDGE_PREFIX}${RENDER_ONLY_NODE_PREFIX}${end.nodeId}-${end.route}`,
        source: end.nodeId,
        sourceHandle: end.handleId,
        target: `${RENDER_ONLY_NODE_PREFIX}${end.nodeId}-${end.route}`,
        type: 'ghost',
        selectable: false,
        focusable: false,
      })),
    [spots],
  );

  const realEdges = useMemo<Edge<InsertableEdgeData>[]>(
    () =>
      edges.map((edge) => {
        const source = nodes.find((n) => n.id === edge.source);
        const route = edgeRoute(edge);
        const pill = branchPillText(edge, source);
        return {
          ...edge,
          type: 'insertable',
          sourceHandle: handleFor(edge, source),
          markerEnd: overlay?.edgesTaken.includes(edge.id) ? ARROW_TAKEN : ARROW,
          selected: selectedEdgeId !== null ? edge.id === selectedEdgeId : edge.selected,
          data: { ...(edge.data ?? {}), sourceNodeId: edge.source, route, pill, tone: branchTone(route), onInsertNode: onAddNode, onRemove: onRemoveEdge, onSelect: onSelectEdge, run: overlay ? (overlay.edgesTaken.includes(edge.id) ? 'taken' : 'untaken') : undefined },
        };
      }),
    [edges, nodes, selectedEdgeId, onSelectEdge, onAddNode, onRemoveEdge, overlay],
  );

  const loopBackEdges = useMemo<Edge<InsertableEdgeData>[]>(
    () =>
      loopBacks(nodes, edges, openEnds).map(({ leafId, loopId }) => ({
        id: `${RENDER_ONLY_EDGE_PREFIX}loopback-${leafId}`,
        source: leafId,
        sourceHandle: handleFor({ id: '', source: leafId, target: loopId }, nodes.find((n) => n.id === leafId)),
        target: loopId,
        type: 'insertable',
        selectable: false,
        focusable: false,
        markerEnd: ARROW,
        data: { sourceNodeId: leafId, route: 'next', pill: 'Next item', tone: 'loop', loopBack: true, onInsertNode: onAddNode },
      })),
    [nodes, edges, openEnds, onAddNode],
  );

  const subtitles = useMemo(() => endSubtitles(nodes, edges), [nodes, edges]);
  const facts = useNodeFacts(nodes, edges, overlay, onDeleteNode);
  const order = useMemo(() => stepOrder(nodes), [nodes]);
  // A step whose inputs did not change keeps the very same object, so React Flow and the memoized cards skip it.
  const cache = useRef(new Map<string, { src: Node<FlowNodeData>; key: string; fact: unknown; out: Node<FlowNodeData> }>());
  const renderedNodes = useMemo(() => {
    const selected = withSelection(nodes, selectedNodeId);
    const seen = new Set<string>();
    const real = selected.map((n) => {
      seen.add(n.id);
      const fact = facts.get(n.id);
      const overlaid = overlay?.nodes[n.id];
      const description = subtitles.get(n.id);
      const title = cardTitle(n.data);
      const aria = stepAriaLabel(order.get(n.id) ?? 0, nodes.length, title, fact?.status.text ?? '');
      const key = [n.selected ? 1 : 0, description ?? '', overlay ? (overlaid ? CARD_STATUS_OF[overlaid.status] : 'none') : 'live', overlaid?.summary ?? '', aria].join('|');
      const hit = cache.current.get(n.id);
      if (hit && hit.src === n && hit.key === key && hit.fact === fact) return hit.out;
      const out: Node<FlowNodeData> = {
        ...n,
        ariaLabel: aria,
        data: {
          ...n.data,
          ...(description ? { description } : {}),
          ...(overlay ? { status: overlaid ? CARD_STATUS_OF[overlaid.status] : undefined } : {}),
          runSummary: overlaid?.summary || undefined,
          canvas: fact,
        },
      };
      cache.current.set(n.id, { src: n, key, fact, out });
      return out;
    });
    for (const id of cache.current.keys()) if (!seen.has(id)) cache.current.delete(id);
    return [...real, ...(ghostNodes as unknown as Node<FlowNodeData>[])];
  }, [nodes, ghostNodes, selectedNodeId, subtitles, facts, overlay, order]);
  const renderedEdges = useMemo(() => [...realEdges, ...loopBackEdges, ...ghostEdges], [realEdges, loopBackEdges, ghostEdges]);

  return { renderedNodes, renderedEdges };
}
