import type { Filter } from 'frappe-js-sdk/lib/db/types';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import type { BatchJobDoc } from '@/types/batchJob.types';
import { fetchPaginatedCount } from './utilsApi';

const BATCH_JOB_LIST_FIELDS = [
  'name',
  'agent',
  'provider',
  'status',
  'request_count',
  'submitted_at',
  'completed_at',
  'estimated_cost',
  'agent_trigger',
  'creation',
];

/**
 * Pagination parameters for fetching batch jobs.
 */
export interface GetBatchJobsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: string;
  provider?: string;
  filters?: Array<[string, string, unknown]>;
}

export interface PaginatedBatchJobsResponse {
  items: BatchJobDoc[];
  hasMore: boolean;
  total?: number;
}

/**
 * Fetch batch jobs from Frappe. Supports pagination, and filtering by
 * agent (via search), status, and provider -- mirrors the `limit + 1`
 * pattern used by `getAgentRuns`.
 */
export async function getBatchJobs(
  params?: GetBatchJobsParams
): Promise<PaginatedBatchJobsResponse> {
  try {
    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
      status,
      provider,
      filters: passedFilters,
    } = params || {};

    const filters: Array<[string, string, unknown]> = [];

    if (search && search.trim()) {
      filters.push(['agent', 'like', `%${search.trim()}%`]);
    }

    if (status && status !== 'all') {
      filters.push(['status', '=', status]);
    }

    if (provider && provider !== 'all') {
      filters.push(['provider', '=', provider]);
    }

    if (passedFilters && passedFilters.length > 0) {
      passedFilters.forEach((filter) => filters.push(filter));
    }

    const jobs = await db.getDocList(doctype['Batch Job'], {
      fields: BATCH_JOB_LIST_FIELDS,
      filters: filters.length > 0 ? (filters as Filter<Record<string, unknown>>[]) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'creation', order: 'desc' },
    });

    const mappedJobs = jobs as BatchJobDoc[];
    const hasMore = mappedJobs.length > limit;
    const items = hasMore ? mappedJobs.slice(0, limit) : mappedJobs;

    const total = await fetchPaginatedCount(page, items.length, doctype['Batch Job'], filters);

    return {
      items,
      hasMore,
      total,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching batch jobs');
    return {
      items: [],
      hasMore: false,
      total: 0,
    };
  }
}

/**
 * Fetch a single batch job by name, including its full result summary.
 */
export async function getBatchJob(name: string): Promise<BatchJobDoc | null> {
  try {
    const job = await db.getDoc(doctype['Batch Job'], name);
    return job as BatchJobDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching batch job ${name}`);
    return null;
  }
}
