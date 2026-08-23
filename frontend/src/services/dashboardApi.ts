import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchDocCount } from './utilsApi';
import { AgentRunDoc } from './agentRunApi';
import { getFlowDefinitions, listFlowRuns } from './flowApi';
import { mapBackendStatusToFrontend } from './flowSerializer';
import type { FlowStatus } from '@/types/flow.types';

export interface DashboardFlowItem {
  id: string;
  name: string;
  status: FlowStatus;
  runCount: number;
  lastRunAt: string | null;
}

/**
 * Get date filters for last 7 days
 */
function getLast7DaysFilters(): Array<[string, string, unknown]> {
  const now = new Date();
  const sevenDaysAgo = new Date(now);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  
  // Format dates as YYYY-MM-DD HH:mm:ss
  const formatDate = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  };

  return [
    ['creation', '>=', formatDate(sevenDaysAgo)],
    ['creation', '<=', formatDate(now)],
  ];
}

/**
 * Fetch the count of agent runs in the last 7 days
 */
export async function getAgentRunsCountLast7Days(): Promise<number> {
  try {
    const filters = getLast7DaysFilters();
    const count = await fetchDocCount(doctype['Agent Run'], filters);
    return count ?? 0;
  } catch (error) {
    handleFrappeError(error, 'Error fetching agent runs count for last 7 days');
    return 0;
  }
}

/**
 * Fetch the last 10 agent runs for dashboard
 */
export async function getRecentAgentRuns(): Promise<AgentRunDoc[]> {
  try {
    const runs = await db.getDocList(doctype['Agent Run'], {
      fields: ['name', 'agent', 'conversation', 'start_time', 'end_time', 'status'],
      limit: 10,
      orderBy: { field: 'creation', order: 'desc' },
    });
    
    return runs as AgentRunDoc[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching recent agent runs');
  }
}

/**
 * Fetch active flows with run stats for the dashboard preview
 */
export async function getDashboardActiveFlows(limit = 10): Promise<DashboardFlowItem[]> {
  try {
    const items = await getFlowDefinitions();
    const active = items
      .filter((f) => f.status === 'Active')
      .slice(0, limit);

    return Promise.all(
      active.map(async (flow) => {
        try {
          const [runCount, recentRuns] = await Promise.all([
            fetchDocCount(doctype['Flow Run'], [['flow_id', '=', flow.flow_id]]),
            listFlowRuns(flow.flow_id, undefined, 1),
          ]);

          return {
            id: flow.flow_id,
            name: flow.flow_name,
            status: mapBackendStatusToFrontend(flow.status),
            runCount: runCount ?? 0,
            lastRunAt: recentRuns[0]?.started_at ?? null,
          };
        } catch (error) {
          // One flow's run stats being denied/unavailable must not blank the
          // whole active-flows widget - show it with unknown stats instead.
          console.error(`Error fetching run stats for flow ${flow.flow_id}:`, error);
          return {
            id: flow.flow_id,
            name: flow.flow_name,
            status: mapBackendStatusToFrontend(flow.status),
            runCount: 0,
            lastRunAt: null,
          };
        }
      })
    );
  } catch (error) {
    handleFrappeError(error, 'Error fetching dashboard active flows');
    return [];
  }
}
