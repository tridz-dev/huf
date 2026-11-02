import { useMemo } from 'react';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { validateFlow, type FlowIssue } from '@/lib/flow-graph/flowValidation';

/**
 * What is left to finish in the open flow, computed from the flow itself each time it changes (nothing is stored,
 * so it can never go stale). People who cannot edit the flow are not shown a to-do list.
 */
export function useFlowIssues(): FlowIssue[] {
  const { activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  return useMemo(() => (activeFlow && canManage ? validateFlow(activeFlow.nodes, activeFlow.edges) : []), [activeFlow, canManage]);
}
