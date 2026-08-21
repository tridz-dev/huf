import type { Filter } from 'frappe-js-sdk/lib/db/types';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchPaginatedCount } from './utilsApi';

const NETWORK_ACCESS_POLICY_LIST_FIELDS = [
  'name',
  'policy_name',
  'modified',
];

export interface NetworkAccessPolicyRuleRow {
  name?: string;
  host_or_cidr: string;
  port_range?: string;
  protocol?: 'https' | 'http' | 'tcp';
}

export interface NetworkAccessPolicyDoc {
  name: string;
  policy_name: string;
  rules: NetworkAccessPolicyRuleRow[];
  modified?: string;
}

export interface GetNetworkAccessPoliciesParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
}

export interface PaginatedNetworkAccessPoliciesResponse {
  items: NetworkAccessPolicyDoc[];
  hasMore: boolean;
  total?: number;
}

export async function getNetworkAccessPolicies(
  params?: GetNetworkAccessPoliciesParams,
): Promise<PaginatedNetworkAccessPoliciesResponse> {
  try {
    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
    } = params || {};

    const filters: Array<[string, string, unknown]> = [];

    if (search && search.trim()) {
      filters.push(['policy_name', 'like', `%${search.trim()}%`]);
    }

    const policies = await db.getDocList(doctype['Network Access Policy'], {
      fields: NETWORK_ACCESS_POLICY_LIST_FIELDS,
      filters: filters.length > 0 ? (filters as Filter<Record<string, unknown>>[]) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mapped = policies as NetworkAccessPolicyDoc[];
    const hasMore = mapped.length > limit;
    const items = hasMore ? mapped.slice(0, limit) : mapped;

    const total = await fetchPaginatedCount(
      page,
      items.length,
      doctype['Network Access Policy'],
      filters,
    );

    return { items, hasMore, total };
  } catch (error) {
    handleFrappeError(error, 'Error fetching network access policies');
  }
}

export async function getNetworkAccessPolicy(name: string): Promise<NetworkAccessPolicyDoc> {
  try {
    const doc = await db.getDoc(doctype['Network Access Policy'], name);
    return doc as NetworkAccessPolicyDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching network access policy ${name}`);
  }
}

export async function createNetworkAccessPolicy(
  data: Partial<NetworkAccessPolicyDoc>,
): Promise<NetworkAccessPolicyDoc> {
  try {
    const created = await db.createDoc(doctype['Network Access Policy'], data);
    return created as NetworkAccessPolicyDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating network access policy');
  }
}

export async function updateNetworkAccessPolicy(
  name: string,
  data: Partial<NetworkAccessPolicyDoc>,
): Promise<NetworkAccessPolicyDoc> {
  try {
    let targetName = name;
    if (
      data.policy_name &&
      data.policy_name.trim() &&
      data.policy_name !== name
    ) {
      await db.renameDoc(doctype['Network Access Policy'], name, data.policy_name);
      targetName = data.policy_name;
    }
    await db.updateDoc(doctype['Network Access Policy'], targetName, data);
    const updated = await db.getDoc(doctype['Network Access Policy'], targetName);
    return updated as NetworkAccessPolicyDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating network access policy ${name}`);
  }
}

export async function deleteNetworkAccessPolicy(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Network Access Policy'], name);
  } catch (error) {
    handleFrappeError(error, `Error deleting network access policy ${name}`);
  }
}
