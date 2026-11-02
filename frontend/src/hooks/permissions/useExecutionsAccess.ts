import { usePermissions } from '@/contexts/PermissionsContext';

/** Which Executions tabs this role may read: analytics need "see all agents", flow runs need the flows role. */
export function useExecutionsAccess() {
  const { hasCapability } = usePermissions();
  const canSeeAnalytics = hasCapability('agent.view_all');
  const canSeeFlowRuns = hasCapability('flows.use');
  const allows = (tab: string) => (tab === 'analytics' ? canSeeAnalytics : tab === 'flow-runs' ? canSeeFlowRuns : true);
  return { canSeeAnalytics, canSeeFlowRuns, allows };
}
