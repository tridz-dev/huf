import { useMemo } from 'react';
import { useFlowRunDetail } from '@/hooks/flow/useFlowRunDetail';
import { overlayFromRun, type NodeRunState } from './story/overlay';

export type { NodeRunState } from './story/overlay';

/**
 * "Run on the canvas": what one run did at each step, for the editor to draw (a status dot and a short summary
 * on hover). `nodes` is keyed by step id; a step the run never reached has no entry. Refreshes while the run is
 * still moving. `runId` null gives an empty overlay.
 */
export function useRunOverlay(runId: string | null): {
  nodes: Record<string, NodeRunState>;
  runStatus: string | null;
  /** The step a failed or waiting run stopped at. */
  currentNodeId: string | null;
  loading: boolean;
} {
  const { run, loading } = useFlowRunDetail(runId);
  const nodes = useMemo(() => (run && runId ? overlayFromRun(run) : {}), [run, runId]);
  return { nodes, runStatus: run?.status ?? null, currentNodeId: run?.current_node_id || null, loading };
}
