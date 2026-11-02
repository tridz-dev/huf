import { useEffect, useState } from 'react';
import { getFlowStepLabels } from '@/services/flowApi';
import type { AgentRunDoc } from '@/services/agentRunApi';

/**
 * Runs made by a flow step (tool call, agent, router) carry no agent of their own: name them
 * "Flow: <flow name> > <step title>" so they read as part of the flow, not "Unknown Agent".
 * Returns `{run name: label}`, filled in as the labels arrive.
 */
export function useFlowStepLabelsFor(runs: AgentRunDoc[]): Record<string, string> {
  const [flowLabels, setFlowLabels] = useState<Record<string, string>>({});
  useEffect(() => {
    const wanted = runs.filter((r) => r.flow_run && !(r.name in flowLabels));
    if (wanted.length === 0) return;
    let cancelled = false;
    getFlowStepLabels(wanted.map((r) => ({ flow_run: r.flow_run as string, flow_node_id: r.flow_node_id }))).then((labels) => {
      if (cancelled) return;
      setFlowLabels((prev) => {
        const next = { ...prev };
        wanted.forEach((r, i) => {
          next[r.name] = labels[i] ?? '';
        });
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs]);
  return flowLabels;
}
