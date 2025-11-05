import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AIProvider, AIModel } from '@/types/agent.types';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Fetch all AI Providers from Frappe
 */
export async function getProviders(): Promise<AIProvider[]> {
  try {
    const providers = await db.getDocList(doctype['AI Provider'], {
      fields: ['name', 'provide_name'],
      limit: 1000,
    });
    return providers.map((p: any) => ({
      name: p.name,
      provider_name: p.provide_name || p.name,
    })) as AIProvider[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching providers');
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

