import type { Filter } from 'frappe-js-sdk/lib/db/types';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { MemoryPolicyDoc } from '@/types/memory';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchPaginatedCount } from './utilsApi';

const MEMORY_POLICY_LIST_FIELDS = [
  'name',
  'policy_name',
  'description',
  'enabled',
  'agent',
  'scope_type',
  'capture_mode',
  'inject_mode',
  'approval_required',
  'auto_promote_to_knowledge',
  'modified',
];

export interface GetMemoryPoliciesParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: string;
}

export interface PaginatedMemoryPoliciesResponse {
  items: MemoryPolicyDoc[];
  hasMore: boolean;
  total?: number;
}

export async function getMemoryPolicies(
  params?: GetMemoryPoliciesParams,
): Promise<PaginatedMemoryPoliciesResponse> {
  try {
    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
      status,
    } = params || {};

    const filters: Array<[string, string, unknown]> = [];

    if (status && status !== 'all') {
      filters.push(['enabled', '=', status === 'enabled' ? 1 : 0]);
    }

    if (search && search.trim()) {
      filters.push(['policy_name', 'like', `%${search.trim()}%`]);
    }

    const policies = await db.getDocList(doctype['Memory Policy'], {
      fields: MEMORY_POLICY_LIST_FIELDS,
      filters: filters.length > 0 ? (filters as Filter<Record<string, unknown>>[]) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mapped = policies as MemoryPolicyDoc[];
    const hasMore = mapped.length > limit;
    const items = hasMore ? mapped.slice(0, limit) : mapped;

    const total = await fetchPaginatedCount(
      page,
      items.length,
      doctype['Memory Policy'],
      filters,
    );

    return { items, hasMore, total };
  } catch (error) {
    handleFrappeError(error, 'Error fetching memory policies');
  }
}

export async function getMemoryPolicy(name: string): Promise<MemoryPolicyDoc> {
  try {
    const doc = await db.getDoc(doctype['Memory Policy'], name);
    return doc as MemoryPolicyDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching memory policy ${name}`);
  }
}

export async function createMemoryPolicy(
  data: Partial<MemoryPolicyDoc>,
): Promise<MemoryPolicyDoc> {
  try {
    const created = await db.createDoc(doctype['Memory Policy'], data);
    return created as MemoryPolicyDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating memory policy');
  }
}

export async function updateMemoryPolicy(
  name: string,
  data: Partial<MemoryPolicyDoc>,
): Promise<MemoryPolicyDoc> {
  try {
    let targetName = name;
    if (
      data.policy_name &&
      data.policy_name.trim() &&
      data.policy_name !== name
    ) {
      await db.renameDoc(doctype['Memory Policy'], name, data.policy_name);
      targetName = data.policy_name;
    }
    await db.updateDoc(doctype['Memory Policy'], targetName, data);
    const updated = await db.getDoc(doctype['Memory Policy'], targetName);
    return updated as MemoryPolicyDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating memory policy ${name}`);
  }
}

export async function deleteMemoryPolicy(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Memory Policy'], name);
  } catch (error) {
    handleFrappeError(error, `Error deleting memory policy ${name}`);
  }
}
