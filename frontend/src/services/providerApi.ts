import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AIProvider, AIModel } from '@/types/agent.types';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchDocCount } from './utilsApi';

/**
 * Pagination parameters for fetching providers
 */
export interface GetProvidersParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
}

/**
 * Paginated response for providers
 */
export interface PaginatedProvidersResponse {
  items: AIProvider[];
  hasMore: boolean;
  total?: number;
}

/**
 * Fetch AI Providers from Frappe
 * Supports pagination and search
 */
export async function getProviders(
  params?: GetProvidersParams
): Promise<PaginatedProvidersResponse | AIProvider[]> {
  try {
    // Backward compatibility: if no params, return array (old API)
    if (!params) {
      const providers = await db.getDocList(doctype['AI Provider'], {
        fields: ['name', 'provide_name'],
        limit: 1000,
      });
      return providers.map((p: any) => ({
        name: p.name,
        provider_name: p.provide_name || p.name,
      })) as AIProvider[];
    }

    const {
      page = 1,
      limit = 10,
      start = (page - 1) * limit,
      search,
    } = params;

    // Build filters
    const filters: Array<[string, string, unknown]> = [];

    // Build search filters if provided
    if (search && search.trim()) {
      filters.push(['provide_name', 'like', `%${search.trim()}%`]);
    }

    // Fetch data
    const providers = await db.getDocList(doctype['AI Provider'], {
      fields: ['name', 'provide_name'],
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1, // Fetch one extra to check if there's more
      ...(start > 0 && { limit_start: start }), // Only include if start > 0
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedProviders = providers.map((p: any) => ({
      name: p.name,
      provider_name: p.provide_name || p.name,
    })) as AIProvider[];

    const hasMore = mappedProviders.length > limit;
    const items = hasMore ? mappedProviders.slice(0, limit) : mappedProviders;

    // Only fetch count on first page to avoid unnecessary API calls
    let total: number | undefined;
    if (page === 1) {
      try {
        const countFilters = [...filters];
        total = await fetchDocCount(doctype['AI Provider'], countFilters);
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
    handleFrappeError(error, 'Error fetching providers');
    return {
      items: [],
      hasMore: false,
      total: 0,
    };
  }
}

/**
 * AI Provider document from Frappe
 */
export interface AIProviderDoc {
  name: string;
  provide_name: string;
  api_key?: string;
  slug?: string;
  chef?: string;
}

/**
 * Fetch a single AI Provider by name
 */
export async function getProvider(name: string): Promise<AIProviderDoc> {
  try {
    const provider = await db.getDoc(doctype['AI Provider'], name);
    return provider as AIProviderDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching provider ${name}`);
  }
}

/**
 * Update an AI Provider document
 */
export async function updateProvider(name: string, data: Partial<AIProviderDoc>): Promise<AIProviderDoc> {
  try {
    await db.updateDoc(doctype['AI Provider'], name, data);
    const updatedProvider = await db.getDoc(doctype['AI Provider'], name);
    return updatedProvider as AIProviderDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating provider ${name}`);
  }
}

/**
 * Fetch all AI Models from Frappe
 */
export async function getModels(providerId?: string): Promise<AIModel[]> {
  try {
    const models = await db.getDocList(doctype['AI Model'], {
      fields: ['name', 'model_name', 'provider'],
      filters: providerId ? [['provider', '=', providerId]] : undefined,
      limit: 1000,
    });
    return models.map((m: any) => ({
      name: m.name,
      model_name: m.model_name || m.name,
      provider: m.provider,
    })) as AIModel[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching models');
  }
}

