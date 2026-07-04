/**
 * Integration Settings API functions
 *
 * Manages external service credentials (Slack, Telegram, GitHub, etc.)
 */

import { db, call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchPaginatedCount } from './utilsApi';
import { doctype } from '@/data/doctypes';
import type {
  IntegrationServiceDoc,
  IntegrationSettingsDoc,
} from '@/types/integration.types';

export interface GetIntegrationSettingsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  service?: string;
  category?: string;
}

export interface PaginatedIntegrationSettingsResponse {
  items: IntegrationSettingsDoc[];
  hasMore: boolean;
  total?: number;
}

const LIST_FIELDS = [
  'name',
  'service',
  'is_active',
  'is_default',
  'last_used',
  'last_error',
  'modified',
] as const;

export async function getIntegrationServices(): Promise<IntegrationServiceDoc[]> {
  try {
    const response = await db.getDocList(doctype['Integration Service'], {
      fields: [
        'name',
        'service_name',
        'category',
        'description',
        'documentation_url',
        'required_credentials',
        'is_builtin',
      ],
      orderBy: { field: 'category', order: 'asc' },
      limit: 100,
    });
    return response as IntegrationServiceDoc[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching integration services');
    return [];
  }
}

export async function getIntegrationService(
  serviceName: string,
): Promise<IntegrationServiceDoc> {
  try {
    const response = await db.getDoc(doctype['Integration Service'], serviceName);
    return response as IntegrationServiceDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function getIntegrationSettings(
  params?: GetIntegrationSettingsParams,
): Promise<PaginatedIntegrationSettingsResponse | IntegrationSettingsDoc[]> {
  try {
    if (!params) {
      const response = await db.getDocList(doctype['Integration Settings'], {
        fields: [...LIST_FIELDS],
        orderBy: { field: 'modified', order: 'desc' },
        limit: 100,
      });
      return response as IntegrationSettingsDoc[];
    }

    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
      service,
    } = params;

    const filters: Array<[string, string, unknown]> = [];

    if (search?.trim()) {
      filters.push(['name', 'like', `%${search.trim()}%`]);
    }
    if (service && service !== 'all') {
      filters.push(['service', '=', service]);
    }

    const settings = await db.getDocList(doctype['Integration Settings'], {
      fields: [...LIST_FIELDS],
      filters: filters.length > 0 ? (filters as never) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mapped = settings as IntegrationSettingsDoc[];
    const hasMore = mapped.length > limit;
    const items = hasMore ? mapped.slice(0, limit) : mapped;

    const total = await fetchPaginatedCount(
      page,
      items.length,
      doctype['Integration Settings'],
      filters,
    );

    return { items, hasMore, total };
  } catch (error) {
    handleFrappeError(error, 'Error fetching integration settings');
    throw error;
  }
}

export async function getIntegrationSetting(
  name: string,
): Promise<IntegrationSettingsDoc> {
  try {
    const response = await db.getDoc(doctype['Integration Settings'], name);
    return response as IntegrationSettingsDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function createIntegrationSetting(
  data: Partial<IntegrationSettingsDoc>,
): Promise<IntegrationSettingsDoc> {
  try {
    const response = await db.createDoc(doctype['Integration Settings'], data);
    return response as IntegrationSettingsDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateIntegrationSetting(
  name: string,
  data: Partial<IntegrationSettingsDoc>,
): Promise<IntegrationSettingsDoc> {
  try {
    const response = await db.updateDoc(doctype['Integration Settings'], name, data);
    return response as IntegrationSettingsDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteIntegrationSetting(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Integration Settings'], name);
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function setupTelegramWebhook(
  name: string,
): Promise<{ status?: string }> {
  try {
    const response = await call.post('frappe.client.run_doc_method', {
      dt: doctype['Integration Settings'],
      dn: name,
      method: 'setup_telegram_webhook',
    });
    return (response.message ?? response) as { status?: string };
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}
