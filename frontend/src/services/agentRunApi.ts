import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchDocCount } from './utilsApi';

/**
 * Agent Run document from Frappe
 */
export interface AgentRunDoc {
  name: string;
  agent: string;
  conversation?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  status?: string;
}

/**
 * Pagination parameters for fetching agent runs
 */
export interface GetAgentRunsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: 'Started' | 'Queued' | 'Success' | 'Failed' | 'all';
  agents?: string[];
  filters?: Array<[string, string, unknown]>
}

/**
 * Paginated response for agent runs
 */
export interface PaginatedAgentRunsResponse {
  items: AgentRunDoc[];
  hasMore: boolean;
  total?: number;
}

/**
 * Fetch agent runs from Frappe
 * Supports pagination and search by agent name
 */
export async function getAgentRuns(
  params?: GetAgentRunsParams
): Promise<PaginatedAgentRunsResponse | AgentRunDoc[]> {
  try {
    // Backward compatibility: if no params, return simple array
    if (!params) {
      const runs = await db.getDocList(doctype['Agent Run'], {
        fields: ['name', 'agent', 'start_time', 'end_time', 'status', 'is_child'],
        limit: 1000,
        orderBy: { field: 'creation', order: 'desc' },
      });
      return runs as AgentRunDoc[];
    }

    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
      status,
      agents,
      filters:passedFilters
    } = params;

    // Build filters
    const filters: Array<[string, string, unknown]> = [];

    if (search && search.trim()) {
      filters.push(['agent', 'like', `%${search.trim()}%`]);
    }

    if (status && status !== 'all') {
      filters.push(['status', '=', status]);
    }

    if (agents && agents.length > 0) {
      filters.push(['agent', 'in', agents]);
    }

    if (passedFilters && passedFilters?.length>0){
      passedFilters.forEach((fil)=>filters.push(fil))
    }

    // Fetch data
    const runs = await db.getDocList(doctype['Agent Run'], {
      fields: ['name', 'agent', 'start_time', 'end_time', 'status', 'is_child'],
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1, // Fetch one extra to check if there's more
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'creation', order: 'desc' },
    });

    const mappedRuns = runs as AgentRunDoc[];
    const hasMore = mappedRuns.length > limit;
    const items = hasMore ? mappedRuns.slice(0, limit) : mappedRuns;

    // Only fetch count on first page
    let total: number | undefined;
    if (page === 1) {
      try {
        const countFilters = [...filters];
        total = await fetchDocCount(doctype['Agent Run'], countFilters);
      } catch {
        // Ignore count errors - total is optional
      }
    }

    return {
      items,
      hasMore,
      total,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching agent runs');
    return {
      items: [],
      hasMore: false,
      total: 0,
    };
  }
}


