import { call, db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AIProvider, AIModel } from '@/types/agent.types';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchPaginatedCount } from './utilsApi';

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
 * Pagination parameters for fetching models
 */
export interface GetModelsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  provider?: string;
}

/**
 * Paginated response for models
 */
export interface PaginatedModelsResponse {
  items: AIModel[];
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
        fields: ['name', 'provider_name'],
        limit: 1000,
      });
      return providers.map((p: any) => ({
        name: p.name,
        provider_name: p.provider_name || p.name,
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
      filters.push(['provider_name', 'like', `%${search.trim()}%`]);
    }

    // Fetch data
    const providers = await db.getDocList(doctype['AI Provider'], {
      fields: ['name', 'provider_name'],
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1, // Fetch one extra to check if there's more
      ...(start > 0 && { limit_start: start }), // Only include if start > 0
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedProviders = providers.map((p: any) => ({
      name: p.name,
      provider_name: p.provider_name || p.name,
    })) as AIProvider[];

    const hasMore = mappedProviders.length > limit;
    const items = hasMore ? mappedProviders.slice(0, limit) : mappedProviders;

    const total = await fetchPaginatedCount(
      page,
      items.length,
      doctype['AI Provider'],
      filters
    );

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
  provider_name: string;
  api_key?: string;
  slug?: string;
  chef?: string;
}

/**
 * AI Model document from Frappe
 */
export interface AIModelDoc {
  name: string;
  model_name: string;
  provider: string;
  modalities?: string | null;
}

export interface ModalityOption {
  label: string;
  value: string;
  description?: string;
}

/**
 * Fetch modality options from the backend
 */
export async function getModalities(): Promise<ModalityOption[]> {
  try {
    const response = await call.get('huf.huf.doctype.ai_model.ai_model.get_modalities');
    const values = response.message as string[];
    return values.map(value => ({ label: value, value }));
  } catch (error) {
    handleFrappeError(error, 'Error fetching modality options');
    return [];
  }
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
 * Create a new AI Provider document
 */
export async function createProvider(data: Partial<AIProviderDoc>): Promise<AIProviderDoc> {
  try {
    const newProvider = await db.createDoc(doctype['AI Provider'], data);
    return newProvider as AIProviderDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating provider');
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
        fields: ['name', 'model_name', 'provider', 'modalities'],
        filters: providerId ? [['provider', '=', providerId]] : undefined,
        limit: 1000,
      });
      return models.map((m: any) => ({
        name: m.name,
        model_name: m.model_name || m.name,
        provider: m.provider,
        modalities: m.modalities,
      })) as AIModel[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching models');
    return [];
  }
}

/**
 * Fetch AI Models from Frappe
 * Supports pagination, search, and provider filtering
 */
export async function getModelsPaginated(
  params?: GetModelsParams
): Promise<PaginatedModelsResponse | AIModel[]> {
  try {
    // Backward compatibility: if no params, return array (old API)
    if (!params) {
      return getModels();
    }

    const {
      page = 1,
      limit = 10,
      start = (page - 1) * limit,
      search,
      provider,
    } = params;

    const filters: Array<[string, string, unknown]> = [];

    if (search && search.trim()) {
      filters.push(['model_name', 'like', `%${search.trim()}%`]);
    }

    if (provider && provider.trim()) {
      filters.push(['provider', '=', provider.trim()]);
    }

    const models = await db.getDocList(doctype['AI Model'], {
      fields: ['name', 'model_name', 'provider', 'modalities'],
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedModels = models.map((m: any) => ({
      name: m.name,
      model_name: m.model_name || m.name,
      provider: m.provider,
      modalities: m.modalities,
    })) as AIModel[];

    const hasMore = mappedModels.length > limit;
    const items = hasMore ? mappedModels.slice(0, limit) : mappedModels;

    const total = await fetchPaginatedCount(page, items.length, doctype['AI Model'], filters);

    return {
      items,
      hasMore,
      total,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching models');
    return {
      items: [],
      hasMore: false,
      total: 0,
    };
  }
}

/**
 * Fetch a single AI Model by name
 */
export async function getModel(name: string): Promise<AIModelDoc> {
  try {
    const model = await db.getDoc(doctype['AI Model'], name);
    return model as AIModelDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching model ${name}`);
    throw error;
  }
}

/**
 * Create a new AI Model document
 */
export async function createModel(data: Partial<AIModelDoc>): Promise<AIModelDoc> {
  try {
    const newModel = await db.createDoc(doctype['AI Model'], data);
    return newModel as AIModelDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating model');
    throw error;
  }
}

/**
 * Update an AI Model document
 */
export async function updateModel(name: string, data: Partial<AIModelDoc>): Promise<AIModelDoc> {
  try {
    let targetName = name;

    if (data.model_name && data.model_name.trim().length > 0 && data.model_name !== name) {
      try {
        await db.renameDoc(doctype['AI Model'], name, data.model_name);
        targetName = data.model_name;
      } catch (error: any) {
        console.warn('rename_doc failed, falling back to updateDoc', error);
        targetName = name;
      }
    }

    await db.updateDoc(doctype['AI Model'], targetName, data);
    const updatedModel = await db.getDoc(doctype['AI Model'], targetName);
    return updatedModel as AIModelDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating model ${name}`);
    throw error;
  }
}

