import { call, db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';
import { fetchDocCount, fetchPaginatedCount } from './utilsApi';

export interface AgentSummaryPromptDoc {
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
  category?: string;
}

export interface GetAgentSummaryPromptsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: 'active' | 'inactive' | 'all';
  [key: string]: unknown;
}

export interface PaginatedAgentSummaryPromptsResponse {
  items: AgentSummaryPromptDoc[];
  hasMore: boolean;
  total?: number;
}

export interface AgentSummaryPromptUsageAgent {
  name: string;
  agent_name?: string;
}

export async function getAgentSummaryPrompts(
  params?: GetAgentSummaryPromptsParams
): Promise<PaginatedAgentSummaryPromptsResponse | AgentSummaryPromptDoc[]> {
  try {
    if (!params) {
      const response = await db.getDocList(doctype['Agent Summary Prompt'], {
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

      return response as AgentSummaryPromptDoc[];
    }

    const { page = 1, limit = 20, start = (page - 1) * limit, search, status = 'all' } = params;
    const filters: Array<[string, string, string | number | boolean]> = [];

    if (status === 'active') {
      filters.push(['is_active', '=', 1]);
    } else if (status === 'inactive') {
      filters.push(['is_active', '=', 0]);
    }

    if (search && search.trim()) {
      filters.push(['title', 'like', `%${search.trim()}%`]);
    }

    const prompts = await db.getDocList(doctype['Agent Summary Prompt'], {
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
      filters: filters.length > 0 ? (filters as never) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedPrompts = prompts as AgentSummaryPromptDoc[];
    const hasMore = mappedPrompts.length > limit;
    const items = hasMore ? mappedPrompts.slice(0, limit) : mappedPrompts;
    const total = await fetchPaginatedCount(page, items.length, doctype['Agent Summary Prompt'], filters);

    return {
      items,
      hasMore,
      total,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching Agent Summary Prompts');
    throw error;
  }
}

export async function getAgentSummaryPrompt(name: string): Promise<AgentSummaryPromptDoc> {
  try {
    const response = await db.getDoc(doctype['Agent Summary Prompt'], name);
    return response as AgentSummaryPromptDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function createAgentSummaryPrompt(data: Partial<AgentSummaryPromptDoc>): Promise<AgentSummaryPromptDoc> {
  try {
    const response = await db.createDoc(doctype['Agent Summary Prompt'], data);
    return response as AgentSummaryPromptDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateAgentSummaryPrompt(
  name: string,
  data: Partial<AgentSummaryPromptDoc>
): Promise<AgentSummaryPromptDoc> {
  try {
    const response = await db.updateDoc(doctype['Agent Summary Prompt'], name, data);
    return response as AgentSummaryPromptDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteAgentSummaryPrompt(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Agent Summary Prompt'], name);
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function getAgentSummaryPromptUsageCount(name: string): Promise<number> {
  const count = await fetchDocCount(doctype.Agent, [['summary_prompt_template', '=', name]]);
  return count ?? 0;
}

export async function getAgentsUsingSummaryPrompt(name: string): Promise<AgentSummaryPromptUsageAgent[]> {
  try {
    const response = await db.getDocList(doctype.Agent, {
      fields: ['name', 'agent_name'],
      filters: [['summary_prompt_template', '=', name]],
      limit: 1000,
      orderBy: { field: 'modified', order: 'desc' },
    });

    return response as AgentSummaryPromptUsageAgent[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching summary prompt usage agents');
    throw error;
  }
}

export interface AgentSummaryPromptVersionResult {
  name: string;
  version: number;
}

export async function createAgentSummaryPromptNewVersion(
  promptName: string,
  promptBody: string,
  title?: string,
  description?: string
): Promise<AgentSummaryPromptVersionResult> {
  try {
    const response = await call.post('huf.ai.prompt_api.create_new_summary_version', {
      prompt_name: promptName,
      prompt_body: promptBody,
      title,
      description,
    });

    return response?.message as AgentSummaryPromptVersionResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function forkAgentSummaryPrompt(
  promptName: string,
  title?: string
): Promise<AgentSummaryPromptVersionResult> {
  try {
    const response = await call.post('huf.ai.prompt_api.fork_summary_prompt', {
      prompt_name: promptName,
      title,
    });

    return response?.message as AgentSummaryPromptVersionResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}
