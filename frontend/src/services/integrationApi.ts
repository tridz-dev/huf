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
  AttachServiceToolsPayload,
  AttachServiceToolsResponse,
  CreateIntegrationServicePayload,
  IntegrationServiceDoc,
  IntegrationSettingsDoc,
  ServiceTool,
  UpdateIntegrationServicePayload,
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

export interface GetIntegrationServicesParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  category?: string;
}

export interface PaginatedIntegrationServicesResponse {
  items: IntegrationServiceDoc[];
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
  'display_label',
  'last_test_status',
  'last_test_at',
  'last_test_message',
  'account_label',
  'modified',
] as const;

const SERVICE_LIST_FIELDS = [
  'name',
  'service_name',
  'category',
  'surface',
  'description',
  'documentation_url',
  'required_credentials',
  'is_builtin',
  'modified',
] as const;

export async function getIntegrationServices(): Promise<IntegrationServiceDoc[]> {
  try {
    const response = await db.getDocList(doctype['Integration Service'], {
      fields: [
        'name',
        'service_name',
        'category',
        'surface',
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

export async function getIntegrationServicesPaginated(
  params?: GetIntegrationServicesParams,
): Promise<PaginatedIntegrationServicesResponse> {
  try {
    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
      category,
    } = params ?? {};

    const filters: Array<[string, string, unknown]> = [];

    if (search?.trim()) {
      filters.push(['service_name', 'like', `%${search.trim()}%`]);
    }
    if (category && category !== 'all') {
      filters.push(['category', '=', category]);
    }

    const services = await db.getDocList(doctype['Integration Service'], {
      fields: [...SERVICE_LIST_FIELDS],
      filters: filters.length > 0 ? (filters as never) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mapped = services as IntegrationServiceDoc[];
    const hasMore = mapped.length > limit;
    const items = hasMore ? mapped.slice(0, limit) : mapped;

    const total = await fetchPaginatedCount(
      page,
      items.length,
      doctype['Integration Service'],
      filters,
    );

    return { items, hasMore, total };
  } catch (error) {
    handleFrappeError(error, 'Error fetching integration services');
    throw error;
  }
}

export async function createIntegrationService(
  data: CreateIntegrationServicePayload,
): Promise<IntegrationServiceDoc> {
  try {
    const response = await db.createDoc(doctype['Integration Service'], data);
    return response as IntegrationServiceDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateIntegrationService(
  name: string,
  data: UpdateIntegrationServicePayload,
): Promise<IntegrationServiceDoc> {
  try {
    let targetName = name;
    if (
      data.service_name &&
      typeof data.service_name === 'string' &&
      data.service_name.trim() &&
      data.service_name !== name
    ) {
      await db.renameDoc(doctype['Integration Service'], name, data.service_name);
      targetName = data.service_name;
    }
    const response = await db.updateDoc(doctype['Integration Service'], targetName, data);
    return response as unknown as IntegrationServiceDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteIntegrationService(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Integration Service'], name);
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

    // A connection is found by the name the user gave it, the account it is connected to, or its id.
    const like = search?.trim() ? `%${search.trim()}%` : '';
    const orFilters: Array<[string, string, unknown]> = like
      ? [['display_label', 'like', like], ['account_label', 'like', like], ['name', 'like', like], ['service', 'like', like]]
      : [];
    if (service && service !== 'all') {
      filters.push(['service', '=', service]);
    }

    const settings = await db.getDocList(doctype['Integration Settings'], {
      fields: [...LIST_FIELDS],
      filters: filters.length > 0 ? (filters as never) : undefined,
      ...(orFilters.length > 0 && { orFilters: orFilters as never }),
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mapped = settings as IntegrationSettingsDoc[];
    const hasMore = mapped.length > limit;
    const items = hasMore ? mapped.slice(0, limit) : mapped;

    const total = like
      ? items.length
      : await fetchPaginatedCount(page, items.length, doctype['Integration Settings'], filters);

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

export async function getServiceTools(service: string): Promise<ServiceTool[]> {
  try {
    const response = await call.post('huf.ai.tools.integration_utils.get_service_tools', {
      service,
    });
    const result = (response.message ?? response) as { success?: boolean; tools?: ServiceTool[] };
    return result.tools ?? [];
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function attachServiceTools(
  payload: AttachServiceToolsPayload,
): Promise<AttachServiceToolsResponse> {
  try {
    const response = await call.post('huf.ai.tools.integration_utils.attach_service_tools', {
      service: payload.service,
      tool_names: payload.tool_names,
      agents: payload.agents,
    });
    return (response.message ?? response) as AttachServiceToolsResponse;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface ConnectionTestResult {
  status: 'Connected' | 'Rejected' | 'Not connected';
  /**
   * ok | no_credentials (nothing saved) | missing_credentials (some saved) | rejected | missing_permission
   * | unreachable (could not ask the service: says nothing about the credentials).
   */
  code?: 'ok' | 'no_credentials' | 'missing_credentials' | 'rejected' | 'missing_permission' | 'unreachable';
  message: string;
  /** Workspace or mailbox the credentials connect to. */
  account?: string | null;
  /** Set when the answer was kept on the saved integration. */
  checked_at?: string;
}

/**
 * Harmless read-only check of a Gmail / Slack / Drive / Sheets integration. Typed values are used instead of
 * saved ones and are never stored.
 */
export async function testIntegrationConnection(
  service: string,
  setting?: string,
  credentials?: Record<string, string>,
): Promise<ConnectionTestResult> {
  try {
    const response = await call.post('huf.ai.tools.connection_test.test_connection', {
      service,
      setting,
      credentials: JSON.stringify(credentials ?? {}),
    });
    return (response.message ?? response) as ConnectionTestResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface SlackChannel {
  id: string;
  name: string;
  is_private: boolean;
}

export interface SlackChannelList {
  status: 'Connected' | 'Rejected' | 'Not connected';
  code?: ConnectionTestResult['code'];
  message?: string;
  channels: SlackChannel[];
}

/** Longest the screens wait for the channel list before showing an error with a retry. */
export const SLACK_CHANNELS_TIMEOUT_MS = 15000;

/** Read-only list of the Slack channels the integration's bot can see. Posts nothing. Never waits forever. */
export async function listSlackChannels(setting?: string): Promise<SlackChannelList> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () => reject(new Error('Slack is taking too long to answer. Try again in a moment.')),
      SLACK_CHANNELS_TIMEOUT_MS,
    );
  });
  try {
    const request = call.post('huf.ai.tools.connection_test.list_slack_channels', { setting });
    const response = await Promise.race([request, timeout]);
    return (response.message ?? response) as SlackChannelList;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/** Forget the answer of the last check without testing again (the "Last problem" dismiss). */
export async function clearIntegrationError(name: string): Promise<void> {
  try {
    await db.updateDoc(doctype['Integration Settings'], name, { last_error: '' });
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}
