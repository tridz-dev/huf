import { db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';
import { fetchDocCount, fetchPaginatedCount } from './utilsApi';

export interface AgentPromptDoc {
  name: string;
  title: string;
  slug?: string;
  description?: string;
  is_active: 0 | 1;
  is_system?: 0 | 1;
  visibility?: 'Public' | 'App' | 'Private';
  tags?: string;
  prompt_body: string;
  version?: number;
  is_latest?: 0 | 1;
  previous_version?: string;
  forked_from?: string;
  prompt_group?: string;
  modified?: string;
  categories?: string[]; // Assuming categories are stored as an array of category names
}

export interface GetAgentPromptsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: 'active' | 'inactive' | 'all';
  [key: string]: unknown;
}

export interface PaginatedAgentPromptsResponse {
  items: AgentPromptDoc[];
  hasMore: boolean;
  total?: number;
}

export interface AgentPromptUsageAgent {
  name: string;
  agent_name?: string;
}

export async function getAgentPrompts(
  params?: GetAgentPromptsParams
): Promise<PaginatedAgentPromptsResponse | AgentPromptDoc[]> {
  try {
    if (!params) {
      const response = await db.getDocList(doctype['Agent Prompt'], {
        fields: [
          'name',
          'title',
          'slug',
          'description',
          'is_active',
          'is_system',
          'visibility',
          'tags',
          'version',
          'is_latest',
          'previous_version',
          'forked_from',
          'prompt_group',
          'modified',
        ],
        limit: 100,
        orderBy: { field: 'modified', order: 'desc' },
      });

      return response as AgentPromptDoc[];
    }

    const { page = 1, limit = 20, start = (page - 1) * limit, search, status = 'all' } = params;
    const filters: Array<[string, string, unknown]> = [];

    if (status === 'active') {
      filters.push(['is_active', '=', 1]);
    } else if (status === 'inactive') {
      filters.push(['is_active', '=', 0]);
    }

    if (search && search.trim()) {
      filters.push(['title', 'like', `%${search.trim()}%`]);
    }

    const prompts = await db.getDocList(doctype['Agent Prompt'], {
      fields: [
        'name',
        'title',
        'slug',
        'description',
        'is_active',
        'is_system',
        'visibility',
        'tags',
        'version',
        'is_latest',
        'previous_version',
        'forked_from',
        'prompt_group',
        'modified',
      ],
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedPrompts = prompts as AgentPromptDoc[];
    const hasMore = mappedPrompts.length > limit;
    const items = hasMore ? mappedPrompts.slice(0, limit) : mappedPrompts;
    const total = await fetchPaginatedCount(page, items.length, doctype['Agent Prompt'], filters);

    return {
      items,
      hasMore,
      total,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching Agent Prompts');
    throw error;
  }
}

export async function getAgentPrompt(name: string): Promise<AgentPromptDoc> {
  try {
    const response = await db.getDoc(doctype['Agent Prompt'], name);
    return response as AgentPromptDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function createAgentPrompt(data: Partial<AgentPromptDoc>): Promise<AgentPromptDoc> {
  try {
    const response = await db.createDoc(doctype['Agent Prompt'], data);
    return response as AgentPromptDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateAgentPrompt(
  name: string,
  data: Partial<AgentPromptDoc>
): Promise<AgentPromptDoc> {
  try {
    const response = await db.updateDoc(doctype['Agent Prompt'], name, data);
    return response as AgentPromptDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteAgentPrompt(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Agent Prompt'], name);
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function getAgentPromptUsageCount(name: string): Promise<number> {
  const count = await fetchDocCount(doctype.Agent, [['agent_prompt', '=', name]]);
  return count ?? 0;
}

export async function getAgentsUsingPrompt(name: string): Promise<AgentPromptUsageAgent[]> {
  try {
    const response = await db.getDocList(doctype.Agent, {
      fields: ['name', 'agent_name'],
      filters: [['agent_prompt', '=', name]],
      limit: 1000,
      orderBy: { field: 'modified', order: 'desc' },
    });

    return response as AgentPromptUsageAgent[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching prompt usage agents');
    throw error;
  }
}
