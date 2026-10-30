import { useMemo } from 'react';
import type { Edge, Node } from 'reactflow';
import { useFlowContext } from '@/contexts/FlowContext';
import { useRunOverlay as useRunStates, type NodeRunState } from '@/lib/flow-run/useRunOverlay';
import type { FlowNodeData } from '@/types/flow.types';

/**
 * A run shown on the canvas (UX-18): which steps are done, failed, running, waiting, stopped or skipped, one plain line of
 * what each produced, and which connections the run took. What each step did comes from the run page's own reading of the
 * run (`useRunOverlay` in lib/flow-run, so the canvas and the run details always agree); this file adds what only the
 * canvas knows: the steps the run did not reach, the one it is on, and the connections between steps.
 */
export type OverlayStatus = 'done' | 'failed' | 'running' | 'waiting' | 'stopped' | 'skipped';

export interface RunOverlay {
  nodes: Record<string, { status: OverlayStatus; summary: string }>;
  /** Ids of the connections the run went along. */
  edgesTaken: string[];
}

/** How the canvas card (FlowNodeData.status) calls each overlay status. */
export const CARD_STATUS_OF: Record<OverlayStatus, NonNullable<FlowNodeData['status']>> = {
  done: 'success',
  failed: 'error',
  running: 'running',
  waiting: 'waiting',
  stopped: 'stopped',
  skipped: 'skipped',
};

const FINISHED = new Set(['Success', 'Failed', 'Stopped', 'Cancelled']);
const MOVING = new Set(['Queued', 'Running']);

type StepNode = Pick<Node<FlowNodeData>, 'id' | 'data'>;
type StepEdge = Pick<Edge, 'id' | 'source' | 'target'>;

/** The overlay of one run over the steps and connections of its flow. */
export function buildRunOverlay(
  states: Record<string, NodeRunState>,
  run: { status: string | null; currentNodeId: string | null },
  nodes: StepNode[],
  edges: StepEdge[],
): RunOverlay {
  const out: RunOverlay['nodes'] = {};
  for (const node of nodes) {
    const known = states[node.id];
    if (node.data.nodeType === 'trigger') {
      out[node.id] = { status: 'done', summary: known?.summary ?? '' };
    } else if (known) {
      out[node.id] = { status: known.status, summary: known.summary };
    } else if (node.data.disabled) {
      out[node.id] = { status: 'skipped', summary: 'Turned off' };
    } else if (run.currentNodeId === node.id && run.status && MOVING.has(run.status)) {
      out[node.id] = { status: 'running', summary: 'Running now' };
    } else if (run.status && FINISHED.has(run.status)) {
      out[node.id] = { status: 'skipped', summary: 'This run did not get here' };
    }
  }
  const reached = (id: string) => out[id] !== undefined && out[id].status !== 'skipped';
  return { nodes: out, edgesTaken: edges.filter((e) => reached(e.source) && reached(e.target)).map((e) => e.id) };
}

/** The overlay for run `runId` over the open flow; null when no run is open, it has not loaded yet, or it belongs to another flow. */
export function useRunOverlay(runId: string | null): RunOverlay | null {
  const { activeFlow } = useFlowContext();
  const { nodes: states, runStatus, currentNodeId } = useRunStates(runId);
  const nodes = activeFlow?.nodes;
  const edges = activeFlow?.edges;
  return useMemo(() => {
    if (!runId || !runStatus || !nodes || !edges) return null;
    const keys = Object.keys(states);
    if (keys.length > 0 && !keys.some((id) => nodes.some((n) => n.id === id))) return null; // a run of another flow
    return buildRunOverlay(states, { status: runStatus, currentNodeId }, nodes, edges);
  }, [runId, runStatus, currentNodeId, states, nodes, edges]);
}
