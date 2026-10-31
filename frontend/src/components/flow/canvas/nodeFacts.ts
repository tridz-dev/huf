import { useMemo, useRef } from 'react';
import type { Edge, Node } from 'reactflow';
import { unreachableNodeIds } from '@/lib/flow/flowEdit';
import { cardStatus } from '@/lib/flow/flowNodeCard';
import { isToolUnconnected, useIntegrationStatus } from '@/lib/flow/flowIntegrations';
import { validateNode } from '@/lib/flow-graph/flowValidation';
import { orphanNote } from '@/lib/flow-graph/flowCanvasGraph';
import type { CanvasNodeFacts, FlowNodeData } from '@/types/flow.types';
import { useGatewayRegistry } from '@/hooks/flow/useGatewayRegistry';
import { useViewerGatewayStates } from '@/hooks/flow/useViewerGatewayStates';
import { CARD_STATUS_OF, type RunOverlay } from '@/lib/flow-graph/runOverlay';

type Step = Node<FlowNodeData>;

/** Title shown on a card (the empty trigger always says "Start here"). */
export const cardTitle = (data: FlowNodeData) => (data.nodeType === 'trigger' && !data.triggerConfig?.type ? 'Start here' : data.label);

/** "Step 3 of 7: Send email, needs setup": what a screen reader hears when it reaches a card. */
export function stepAriaLabel(index: number, total: number, title: string, statusText: string): string {
  return `Step ${index} of ${total}: ${title}, ${statusText.toLowerCase()}`;
}

/** Reading order of the steps: top to bottom, then left to right. */
export function stepOrder(nodes: Array<Pick<Step, 'id' | 'position'>>): Map<string, number> {
  const sorted = [...nodes].sort((a, b) => Math.round(a.position.y / 20) - Math.round(b.position.y / 20) || a.position.x - b.position.x);
  return new Map(sorted.map((n, i) => [n.id, i + 1]));
}

interface Cached {
  data: unknown;
  edges: unknown;
  firstIssue: string | null;
  issueCount: number;
  registry: unknown;
  viewer: unknown;
}

/**
 * What every card needs, computed once per change of the flow instead of once per card: the first thing missing in a
 * step, whether anything leads to it, its status word (a run opened on the canvas wins over the last live status).
 * A card's facts object only changes when one of those does, so a drag that moves one step re-renders one card.
 */
export function useNodeFacts(nodes: Step[], edges: Edge[], overlay: RunOverlay | null, onDelete: (nodeId: string) => void): Map<string, CanvasNodeFacts> {
  const integration = useIntegrationStatus();
  // A chat trigger's checklist reads the channel list ("switched off"): recompute when it arrives.
  const { registry } = useGatewayRegistry(false);
  // A view-only person cannot list channels; ask for the on/off state of just the ones this flow uses.
  const viewerRegistry = useViewerGatewayStates(nodes);
  const issues = useRef(new Map<string, Cached>());
  const facts = useRef(new Map<string, CanvasNodeFacts>());
  const reach = useRef<{ edges: unknown; ids: string; set: Set<string> } | null>(null);
  return useMemo(() => {
    const ids = nodes.map((n) => `${n.id}${n.data.nodeType === 'trigger' ? '*' : ''}`).join(',');
    if (!reach.current || reach.current.edges !== edges || reach.current.ids !== ids) {
      reach.current = { edges, ids, set: unreachableNodeIds(nodes, edges) };
    }
    const unreachable = reach.current.set;
    const next = new Map<string, CanvasNodeFacts>();
    for (const n of nodes) {
      let cached = issues.current.get(n.id);
      if (!cached || cached.data !== n.data || cached.edges !== edges || cached.registry !== registry || cached.viewer !== viewerRegistry) {
        const found = validateNode({ id: n.id, data: n.data }, edges);
        cached = { data: n.data, edges, firstIssue: found[0]?.message ?? null, issueCount: found.length, registry, viewer: viewerRegistry };
        issues.current.set(n.id, cached);
      }
      const noLineIn = unreachable.has(n.id) && orphanNote(n.id, nodes, edges) === 'Nothing leads to this step';
      const cfg = n.data.actionConfig as ({ type?: string; tool_id?: unknown }) | undefined;
      const toolId = cfg?.type === 'tool-call' && typeof cfg.tool_id === 'string' && cfg.tool_id ? cfg.tool_id : undefined;
      const overlaid = overlay ? overlay.nodes[n.id] : undefined;
      const runStatus = overlay ? (overlaid ? CARD_STATUS_OF[overlaid.status] : undefined) : n.data.status;
      const isEnd = n.data.nodeType === 'end';
      const isTrigger = n.data.nodeType === 'trigger';
      const status = cardStatus({
        runStatus,
        incomplete: !isEnd && cached.issueCount > 0,
        orphaned: !isTrigger && noLineIn,
        notConnected: !isEnd && !isTrigger && isToolUnconnected(toolId, integration),
      });
      const prev = facts.current.get(n.id);
      const fact: CanvasNodeFacts =
        prev && prev.status.kind === status.kind && prev.firstIssue === cached.firstIssue && prev.orphaned === noLineIn && prev.onDelete === onDelete
          ? prev
          : { status, firstIssue: cached.firstIssue, orphaned: noLineIn, onDelete };
      facts.current.set(n.id, fact);
      next.set(n.id, fact);
    }
    return next;
  }, [nodes, edges, overlay, integration, onDelete, registry, viewerRegistry]);
}
