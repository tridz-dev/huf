import { useMemo } from 'react';
import type { Edge, Node } from 'reactflow';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowRunDetail } from '@/hooks/flow/useFlowRunDetail';
import type { FlowRunDetail } from '@/services/flowApi';
import type { FlowNodeData } from '@/types/flow.types';
import { describeDecision, isFailedStepOutput, titleNodeIds } from '@/lib/flow-run/flowRunFormat';
import { humanizeSentence } from '@/lib/flow-run/humanize';
import { redactSecrets, summarizeToolOutput } from '@/lib/flow/flowToolSummary';

/**
 * A run shown on the canvas (UX-18): which steps are done, failed, running, waiting or skipped, one plain line of what each
 * produced, and which connections the run took. The shape matches `useRunOverlay(runId)` of the run page work
 * (lib/flow-run/useRunOverlay.ts); until that lands this file adapts the existing run API (`get_flow_run`).
 */
export type OverlayStatus = 'done' | 'failed' | 'running' | 'waiting' | 'skipped';

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
  skipped: 'skipped',
};

const SUMMARY_MAX = 110;
const shorten = (text: string) => (text.length > SUMMARY_MAX ? `${text.slice(0, SUMMARY_MAX - 1).trimEnd()}…` : text);

const WAITING = new Set(['Waiting Approval', 'Waiting User', 'Waiting Code']);
const FINISHED = new Set(['Success', 'Failed']);

type StepNode = Pick<Node<FlowNodeData>, 'id' | 'data'>;
type StepEdge = Pick<Edge, 'id' | 'source' | 'target'>;

/** One plain line of what a finished step produced ("Sent a message to #alerts", "Customer: Ada, Total: 450"). */
export function stepSummary(node: StepNode | undefined, output: unknown, failedReason?: string | null): string {
  if (failedReason) return shorten(failedReason);
  if (output === undefined || output === null || output === '') return '';
  const decision = describeDecision(output);
  if (decision) return shorten(decision);
  const cfg = node?.data.actionConfig as { type?: string; tool_id?: string } | undefined;
  const tool = cfg?.type === 'tool-call' ? summarizeToolOutput(cfg.tool_id, output) : null;
  if (tool) return shorten(tool);
  return shorten(humanizeSentence(redactSecrets(titleNodeIds(output, () => null)), {}, 3));
}

/** The overlay of one run over the steps and connections of its flow. */
export function buildRunOverlay(run: Pick<FlowRunDetail, 'status' | 'current_node_id' | 'context_json' | 'last_error'>, nodes: StepNode[], edges: StepEdge[]): RunOverlay {
  const raw = (run.context_json as { __node_outputs__?: unknown } | undefined)?.__node_outputs__;
  const outputs = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const finished = FINISHED.has(run.status);
  const current = run.current_node_id;
  const out: RunOverlay['nodes'] = {};

  for (const node of nodes) {
    const id = node.id;
    const ran = id in outputs;
    if (node.data.nodeType === 'trigger') {
      out[id] = { status: 'done', summary: ran ? stepSummary(node, outputs[id]) : '' };
      continue;
    }
    const isCurrent = id === current;
    if (ran && !(isCurrent && run.status === 'Failed') && !isFailedStepOutput(outputs[id])) {
      out[id] = { status: 'done', summary: stepSummary(node, outputs[id]) };
    } else if (ran || (isCurrent && run.status === 'Failed')) {
      const own = outputs[id] && typeof outputs[id] === 'object' ? (outputs[id] as { error?: unknown }).error : null;
      const reason = typeof own === 'string' && own ? own : isCurrent ? run.last_error : null;
      out[id] = { status: 'failed', summary: shorten(reason || 'This step failed.') };
    } else if (isCurrent && (run.status === 'Running' || run.status === 'Queued')) {
      out[id] = { status: 'running', summary: 'Running now' };
    } else if (isCurrent && WAITING.has(run.status)) {
      out[id] = { status: 'waiting', summary: run.status === 'Waiting Approval' ? 'Waiting for a person to decide' : 'Waiting' };
    } else if (finished || node.data.disabled) {
      out[id] = { status: 'skipped', summary: node.data.disabled ? 'Turned off' : 'This run did not get here' };
    }
  }

  const reached = (id: string) => out[id] !== undefined && out[id].status !== 'skipped';
  const edgesTaken = edges.filter((e) => reached(e.source) && reached(e.target)).map((e) => e.id);
  return { nodes: out, edgesTaken };
}

/** The overlay for run `runId` over the open flow; null when no run is open, it belongs to another flow, or it has not loaded. */
export function useRunOverlay(runId: string | null): RunOverlay | null {
  const { activeFlow } = useFlowContext();
  const { run } = useFlowRunDetail(runId);
  const nodes = activeFlow?.nodes;
  const edges = activeFlow?.edges;
  return useMemo(() => {
    if (!runId || !run || run.flow_run_id !== runId || !nodes || !edges) return null;
    if (activeFlow && run.flow_id !== activeFlow.id) return null;
    return buildRunOverlay(run, nodes, edges);
  }, [runId, run, nodes, edges, activeFlow]);
}
