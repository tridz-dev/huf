import { getAgentRuns, type AgentRunDoc } from '@/services/agentRunApi';
import { toServerDatetime } from '@/lib/serverTime';
import { rangeStart } from './executionsRange';

export interface AgentRunsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: string;
  agents?: string;
  range?: string;
}

/** One page of top-level agent runs for the Executions "Runs" tab, within the picked time window. */
export async function fetchAgentRunsPage(params: AgentRunsParams): Promise<{ data: AgentRunDoc[]; hasMore: boolean; total?: number }> {
  // `range` is only present in params once a non-default value is picked
  // (setFilter drops the key when it equals the "no-op" sentinel — here
  // that's the not-yet-initialized state, so an absent range still means
  // "use the default window", same as the Status/Agent filters below).
  const from = rangeStart(params.range);
  const runFilters: Array<[string, string, unknown]> = [['is_child', '=', '0']];
  if (from) {
    runFilters.push(['start_time', '>=', toServerDatetime(from)]);
  }

  const response = await getAgentRuns({
    page: params.page,
    limit: params.limit,
    start: params.start,
    search: params.search,
    status: params.status as 'Started' | 'Queued' | 'Success' | 'Failed' | 'all' | undefined,
    agents: params.agents ? params.agents.split(',').filter(Boolean) : undefined,
    filters: runFilters,
  });

  if (Array.isArray(response)) {
    return {
      data: response,
      hasMore: false,
      total: response.length,
    };
  }

  return {
    data: response.items,
    hasMore: response.hasMore,
    total: response.total,
  };
}
