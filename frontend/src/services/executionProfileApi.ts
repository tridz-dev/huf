import { db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';
import { fetchPaginatedCount } from './utilsApi';

export interface ExecutionProfileDoc {
  name: string;
  profile_name: string;
  is_builtin?: 0 | 1;
  disabled?: 0 | 1;
  approval_mode?: 'Auto Approve' | 'Ask Every Time' | 'Never Allow';
  filesystem_policy?: 'None' | 'Scratch Only' | 'Shared Directory';
  network_policy?: string;
  allowed_modules?: string;
  max_wall_time_s?: number;
  max_cpu_seconds?: number;
  max_memory_mb?: number;
  max_output_bytes?: number;
  modified?: string;
}

export interface GetExecutionProfilesParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: 'enabled' | 'disabled' | 'all';
  [key: string]: unknown;
}

export interface PaginatedExecutionProfilesResponse {
  items: ExecutionProfileDoc[];
  hasMore: boolean;
  total?: number;
}

export async function getExecutionProfiles(
  params?: GetExecutionProfilesParams
): Promise<PaginatedExecutionProfilesResponse | ExecutionProfileDoc[]> {
  try {
    if (!params) {
      const response = await db.getDocList(doctype['Execution Profile'], {
        fields: [
          'name',
          'profile_name',
          'is_builtin',
          'disabled',
          'approval_mode',
          'filesystem_policy',
          'network_policy',
          'allowed_modules',
          'max_wall_time_s',
          'max_cpu_seconds',
          'max_memory_mb',
          'max_output_bytes',
          'modified',
        ],
        limit: 100,
        orderBy: { field: 'modified', order: 'desc' },
      });

      return response as ExecutionProfileDoc[];
    }

    const { page = 1, limit = 20, start = (page - 1) * limit, search, status = 'all' } = params;
    const filters: Array<[string, string, string | number | boolean]> = [];

    if (status === 'enabled') {
      filters.push(['disabled', '=', 0]);
    } else if (status === 'disabled') {
      filters.push(['disabled', '=', 1]);
    }

    if (search && search.trim()) {
      filters.push(['profile_name', 'like', `%${search.trim()}%`]);
    }

    const profiles = await db.getDocList(doctype['Execution Profile'], {
      fields: [
        'name',
        'profile_name',
        'is_builtin',
        'disabled',
        'approval_mode',
        'filesystem_policy',
        'network_policy',
        'allowed_modules',
        'max_wall_time_s',
        'max_cpu_seconds',
        'max_memory_mb',
        'max_output_bytes',
        'modified',
      ],
      filters: filters.length > 0 ? (filters as never) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedProfiles = profiles as ExecutionProfileDoc[];
    const hasMore = mappedProfiles.length > limit;
    const items = hasMore ? mappedProfiles.slice(0, limit) : mappedProfiles;
    const total = await fetchPaginatedCount(page, items.length, doctype['Execution Profile'], filters);

    return {
      items,
      hasMore,
      total,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching Execution Profiles');
    throw error;
  }
}

export async function getExecutionProfile(name: string): Promise<ExecutionProfileDoc> {
  try {
    const response = await db.getDoc(doctype['Execution Profile'], name);
    return response as ExecutionProfileDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function createExecutionProfile(data: Partial<ExecutionProfileDoc>): Promise<ExecutionProfileDoc> {
  try {
    const response = await db.createDoc(doctype['Execution Profile'], data);
    return response as ExecutionProfileDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateExecutionProfile(
  name: string,
  data: Partial<ExecutionProfileDoc>
): Promise<ExecutionProfileDoc> {
  try {
    const response = await db.updateDoc(doctype['Execution Profile'], name, data);
    return response as ExecutionProfileDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteExecutionProfile(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Execution Profile'], name);
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}
