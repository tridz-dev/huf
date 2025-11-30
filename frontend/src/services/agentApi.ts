import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AgentDoc } from '@/types/agent.types';
import { handleFrappeError } from '@/lib/frappe-error';
import { fetchDocCount } from './utilsApi';

/**
 * Trigger type from API
 */
export interface TriggerTypeOption {
  name: string;
}

/**
 * Fetch trigger types from API
 */
export async function getTriggerTypes(): Promise<TriggerTypeOption[]> {
  try {
    const result = await call.get('huf.huf.doctype.agent_trigger.agent_trigger.get_trigger_type');
    // Handle different response formats
    // Frappe API might return { message: [...] } or just the array directly
    return result.message as TriggerTypeOption[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching trigger types');
  }
}

/**
 * Fields needed for the agents list page
 */
const AGENT_LIST_FIELDS = [
  'name',
  'agent_name',
  'description',
  'model',
  'disabled',
  'last_run',
  'total_run',
];

/**
 * Fields needed for model selector (agents as models)
 */
const AGENT_MODEL_FIELDS = [
  'name',
  'agent_name',
  'chef',
  'slug',
];

/**
 * Fields needed for agent triggers listing
 */
const AGENT_TRIGGER_FIELDS = [
  'name',
  'trigger_name',
  'trigger_type',
  'disabled',
];

/**
 * Agent Trigger document from Frappe (for listing)
 */
export interface AgentTriggerListItem {
  name: string;
  trigger_name: string;
  type: string;
  status: 'active' | 'disabled';
}

/**
 * Map Agent Trigger doctype document to listing format
 */
function mapAgentTriggerListItem(doc: {
  name: string;
  trigger_name: string;
  trigger_type?: string;
  disabled?: 0 | 1;
}): AgentTriggerListItem {
  return {
    name: doc.name,
    trigger_name: doc.trigger_name,
    type: doc.trigger_type || 'Manual',
    status: doc.disabled === 1 ? 'disabled' : 'active',
  };
}


/**
 * Pagination parameters for fetching agents
 */
export interface GetAgentsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: 'active' | 'disabled' | 'all';
}

/**
 * Paginated response for agents
 */
export interface PaginatedAgentsResponse {
  items: AgentDoc[];
  hasMore: boolean;
  total?: number;
}

/**
 * Fetch agents from Frappe
 * Supports pagination, search, and filtering
 */
export async function getAgents(
  params?: GetAgentsParams
): Promise<PaginatedAgentsResponse | AgentDoc[]> {
  try {
    // Backward compatibility: if no params, return array (old API)
    if (!params) {
      const agents = await db.getDocList(doctype.Agent, {
        fields: AGENT_LIST_FIELDS,
        limit: 1000,
      });
      return agents as AgentDoc[];
    }

    const {
      page = 1,
      limit = 20,
      start = (page - 1) * limit,
      search,
      status,
    } = params;

    // Build filters
    const filters: Array<[string, string, unknown]> = [];

    if (status && status !== 'all' && (status === 'disabled' || status === 'active')) {
      filters.push(['disabled', '=', status === 'disabled' ? 1 : 0]);
    }

    // Build search filters if provided
    if (search && search.trim()) {
      filters.push(['agent_name', 'like', `%${search.trim()}%`]);
    }

    // Fetch data
    const agents = await db.getDocList(doctype.Agent, {
      fields: AGENT_LIST_FIELDS,
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1, // Fetch one extra to check if there's more
      ...(start > 0 && { limit_start: start }), // Only include if start > 0
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedAgents = agents as AgentDoc[];
    const hasMore = mappedAgents.length > limit;
    const items = hasMore ? mappedAgents.slice(0, limit) : mappedAgents;

    // Only fetch count on first page to avoid unnecessary API calls
    let total: number | undefined;
    if (page === 1) {
      try {
        const countFilters = [...filters];
        total = await fetchDocCount(doctype.Agent, countFilters);
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
    handleFrappeError(error, 'Error fetching agents');
  }
}

/**
 * Fetch a single agent by name
 * Fetches all fields for detail view
 */
export async function getAgent(name: string): Promise<AgentDoc> {
  try {
    const agent = await db.getDoc(doctype.Agent, name);
    return agent as AgentDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching agent ${name}`);
  }
}

/**
 * Agent Trigger document from Frappe (for editing)
 */
export interface AgentTriggerDoc {
  name: string;
  trigger_name: string;
  agent: string;
  trigger_type?: string;
  disabled?: 0 | 1;
  scheduled_interval?: string;
  interval_count?: number;
  reference_doctype?: string;
  doc_event?: string;
  condition?: string;
}

/**
 * Fetch a single agent trigger by name
 */
export async function getAgentTrigger(triggerName: string): Promise<AgentTriggerDoc> {
  try {
    const trigger = await db.getDoc(doctype['Agent Trigger'], triggerName);
    return trigger as AgentTriggerDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching trigger ${triggerName}`);
  }
}

/**
 * Create a new agent trigger
 */
export async function createAgentTrigger(data: Partial<AgentTriggerDoc>): Promise<AgentTriggerDoc> {
  try {
    const newTrigger = await db.createDoc(doctype['Agent Trigger'], data);
    return newTrigger as AgentTriggerDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating agent trigger');
  }
}

/**
 * Delete an agent trigger
 */
export async function deleteAgentTrigger(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Agent Trigger'], name);
  } catch (error) {
    handleFrappeError(error, `Error deleting trigger ${name}`);
  }
}

/**
 * Update an agent trigger
 */
export async function updateAgentTrigger(name: string, data: Partial<AgentTriggerDoc>): Promise<AgentTriggerDoc> {
  try {
    await db.updateDoc(doctype['Agent Trigger'], name, data);
    const updatedTrigger = await db.getDoc(doctype['Agent Trigger'], name);
    return updatedTrigger as AgentTriggerDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating trigger ${name}`);
  }
}

/**
 * Fetch all DocTypes (for reference_doctype select)
 */
export async function getDocTypes(): Promise<Array<{ name: string }>> {
  try {
    const doctypes = await db.getDocList('DocType', {
      fields: ['name'],
      limit: 1000,
    });
    // Sort alphabetically by name
    return (doctypes as Array<{ name: string }>).sort((a, b) => a.name.localeCompare(b.name));
  } catch (error) {
    handleFrappeError(error, 'Error fetching DocTypes');
  }
}

/**
 * Fetch agent triggers filtered by agent name (for listing)
 */
export async function getAgentTriggers(agentName: string): Promise<AgentTriggerListItem[]> {
  try {
    const triggers = await db.getDocList(doctype['Agent Trigger'], {
      fields: AGENT_TRIGGER_FIELDS,
      filters: [['agent', '=', agentName]],
      limit: 1000,
    });
    return triggers.map(mapAgentTriggerListItem);
  } catch (error) {
    handleFrappeError(error, `Error fetching triggers for agent ${agentName}`);
  }
}

/**
 * Create a new agent document
 */
export async function createAgent(data: Partial<AgentDoc>): Promise<AgentDoc> {
  try {
    // Frappe JS SDK uses createDoc method
    const newAgent = await db.createDoc(doctype.Agent, data);
    return newAgent as AgentDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating agent');
  }
}

/**
 * Update an agent document
 */
export async function updateAgent(name: string, data: Partial<AgentDoc>): Promise<AgentDoc> {
  try {
    await db.updateDoc(doctype.Agent, name, data);
    // Fetch updated document to return
    const updatedAgent = await db.getDoc(doctype.Agent, name);
    return updatedAgent as AgentDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating agent ${name}`);
  }
}

/**
 * Model selector item (agent as model)
 */
export interface AgentModelItem {
  id: string;
  name: string;
  chef: string;
  chefSlug: string;
  providers: string[];
}

/**
 * Pagination parameters for fetching agent models
 */
export interface GetAgentModelsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
}

/**
 * Paginated response for agent models
 */
export interface PaginatedAgentModelsResponse {
  items: AgentModelItem[];
  hasMore: boolean;
  total?: number;
}

/**
 * Fetch agents for model selector
 * Supports pagination and search
 */
export async function getAgentModels(
  params?: GetAgentModelsParams
): Promise<PaginatedAgentModelsResponse> {
  try {
    const {
      page = 1,
      limit = 20,
      start: providedStart,
      search,
    } = params || {};
    
    const start = providedStart ?? (page - 1) * limit;

    // Build filters
    const filters: Array<[string, string, unknown]> = [];

    // Only show agents that allow chat
    filters.push(['allow_chat', '=', 1]);
    filters.push(['disabled', '=', 0]);

    // Build search filters if provided
    if (search && search.trim()) {
      filters.push(['agent_name', 'like', `%${search.trim()}%`]);
    }

    // Fetch data
    const agents = await db.getDocList(doctype.Agent, {
      fields: AGENT_MODEL_FIELDS,
      filters: filters.length > 0 ? (filters as any) : undefined,
      limit: limit + 1, // Fetch one extra to check if there's more
      ...(start > 0 && { limit_start: start }), // Only include if start > 0
      orderBy: { field: 'modified', order: 'desc' },
    });

    // Map agents to model format
    const mappedModels: AgentModelItem[] = (agents as any[]).map((agent) => ({
      id: agent.name,
      name: agent.agent_name || agent.name,
      chef: agent.chef || '',
      chefSlug: agent.slug || '',
      providers: agent.slug ? [agent.slug] : [],
    }));

    const hasMore = mappedModels.length > limit;
    const items = hasMore ? mappedModels.slice(0, limit) : mappedModels;

    // Only fetch count on first page to avoid unnecessary API calls
    let total: number | undefined;
    if (page === 1) {
      try {
        const countFilters = [...filters];
        total = await fetchDocCount(doctype.Agent, countFilters);
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
    handleFrappeError(error, 'Error fetching agent models');
    return {
      items: [],
      hasMore: false,
      total: 0,
    };
  }
}
