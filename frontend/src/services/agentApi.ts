import type { Filter } from 'frappe-js-sdk/lib/db/types';
import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AgentDoc, AgentKnowledgeRow } from '@/types/agent.types';
import { getMCPServer, type MCPServerRef } from '@/services/mcpApi';
import { handleFrappeError } from '@/lib/frappe-error';
import { getBrandLabel } from '@/utils/providerBrands';
import { fetchPaginatedCount } from './utilsApi';

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
  'provider',
  'model',
  'disabled',
  'last_run',
  'total_run',
  'agent_color',
  'allow_chat',
  'prompt_mode',
  'agent_prompt',
  'enable_multi_run',
  'enable_prompt_caching',
  'allow_guest',
  'is_system',
  'provider_brand',
  'modified',
];

/**
 * Fields needed for model selector (agents as models)
 */
const AGENT_MODEL_FIELDS = [
  'name',
  'agent_name',
  'provider_brand',
  'model',
  'agent_color',
  'description',
];

// Only fields that exist on the Agent doctype may be listed here: Frappe
// validates get_list fields for non-System-Manager users and rejects unknown
// ones with HTTP 417 ("Field not permitted in query").
const CHAT_AGENT_FIELDS = [
  'name',
  'agent_name',
  'description',
  'model',
  'agent_color',
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
  chat?: 'all' | 'chat' | 'no_chat';
}

/**
 * Paginated response for agents
 */
export interface PaginatedAgentsResponse {
  items: AgentDoc[];
  hasMore: boolean;
  total?: number;
}

export interface ChatAgentItem {
  name: string;
  agent_name: string;
  description?: string | null;
  model?: string | null;
  agent_color?: string | null;
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
      chat,
    } = params;

    // Build filters
    const filters: Array<[string, string, unknown]> = [];

    if (status && status !== 'all' && (status === 'disabled' || status === 'active')) {
      filters.push(['disabled', '=', status === 'disabled' ? 1 : 0]);
    }

    if (chat === 'chat') {
      filters.push(['allow_chat', '=', 1]);
    } else if (chat === 'no_chat') {
      filters.push(['allow_chat', '=', 0]);
    }

    // Build search filters if provided
    if (search && search.trim()) {
      filters.push(['agent_name', 'like', `%${search.trim()}%`]);
    }

    // Fetch data
    const agents = await db.getDocList(doctype.Agent, {
      fields: AGENT_LIST_FIELDS,
      filters: filters.length > 0 ? (filters as Filter<Record<string, unknown>>[]) : undefined,
      limit: limit + 1, // Fetch one extra to check if there's more
      ...(start > 0 && { limit_start: start }), // Only include if start > 0
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedAgents = agents as AgentDoc[];
    const hasMore = mappedAgents.length > limit;
    const items = hasMore ? mappedAgents.slice(0, limit) : mappedAgents;

    const total = await fetchPaginatedCount(page, items.length, doctype.Agent, filters);

    return {
      items,
      hasMore,
      total,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching agents');
  }
}

export async function getChatAgents(): Promise<ChatAgentItem[]> {
  try {
    const agents = await db.getDocList(doctype.Agent, {
      fields: CHAT_AGENT_FIELDS,
      filters: [
        ['allow_chat', '=', 1],
        ['disabled', '=', 0],
      ],
      limit: 1000,
      orderBy: { field: 'modified', order: 'desc' },
    });

    return agents as ChatAgentItem[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching chat agents');
    return [];
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
 * Child table row for Agent Trigger file attachments (Agent Trigger Attachment)
 */
export interface AgentTriggerAttachmentRow {
  name?: string;
  source_type: 'DocField' | 'Child Table Field';
  child_table?: string;
  field_name: string;
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
  prompt_field?: string;
  file_attachments?: AgentTriggerAttachmentRow[];
  webhook_key?: string;
  webhook_slug?: string;
  app_name?: string;
  event_name?: string;
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
 * Fetch all Frappe roles (for approval role selection, etc.)
 */
export async function getRoles(): Promise<Array<{ name: string }>> {
  try {
    const roles = await db.getDocList('Role', {
      fields: ['name'],
      filters: [['disabled', '=', 0]],
      limit: 500,
    });
    return (roles as Array<{ name: string }>).sort((a, b) => a.name.localeCompare(b.name));
  } catch (error) {
    handleFrappeError(error, 'Error fetching roles');
  }
}

/**
 * DocType metadata field shape (subset of Frappe DocField used by consumers)
 */
export interface DocTypeMetaField {
  fieldname: string;
  label?: string;
  fieldtype?: string;
  reqd?: 0 | 1 | boolean;
  options?: string;
  hidden?: 0 | 1 | boolean;
}

export interface DocTypeMetaResponse {
  fields?: DocTypeMetaField[];
}

/**
 * Fetch DocType metadata with fields (used for tool parameter auto-fill)
 */
export async function getDocTypeMeta(doctypeName: string): Promise<DocTypeMetaResponse> {
  try {
    return (await db.getDoc('DocType', doctypeName)) as DocTypeMetaResponse;
  } catch (error) {
    handleFrappeError(error, `Error fetching DocType meta for ${doctypeName}`);
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
    let targetName = name;
    if (
      data.agent_name &&
      typeof data.agent_name === 'string' &&
      data.agent_name.trim() &&
      data.agent_name !== name
    ) {
      await db.renameDoc(doctype.Agent, name, data.agent_name);
      targetName = data.agent_name;
    }
    await db.updateDoc(doctype.Agent, targetName, data);
    // Fetch updated document to return
    const updatedAgent = await db.getDoc(doctype.Agent, targetName);
    return updatedAgent as AgentDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating agent ${name}`);
  }
}

/**
 * Delete an agent document
 */
export async function deleteAgent(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype.Agent, name);
  } catch (error) {
    handleFrappeError(error, `Error deleting agent ${name}`);
  }
}

/**
 * Duplicate an agent document (copies all fields except identity/stats fields).
 * Ensures the duplicated name is unique by appending "(Copy)", "(Copy 2)", etc.
 */
export async function duplicateAgent(name: string): Promise<AgentDoc> {
  try {
    const source = await db.getDoc(doctype.Agent, name);
    const excludedFields = [
      'name',
      'owner',
      'creation',
      'modified',
      'modified_by',
      'last_run',
      'total_run',
      'idx',
      'docstatus',
    ];
    const rest = Object.fromEntries(
      Object.entries(source as Record<string, unknown>).filter(
        ([key]) => !excludedFields.includes(key)
      )
    );

    const baseName = (source as AgentDoc).agent_name;
    const nameExists = async (candidate: string): Promise<boolean> => {
      const matches = await db.getDocList(doctype.Agent, {
        filters: [['agent_name', '=', candidate]] as any,
        fields: ['name'],
        limit: 1,
      });
      return matches.length > 0;
    };

    let candidateName = `${baseName} (Copy)`;
    let suffix = 2;
    while (await nameExists(candidateName)) {
      candidateName = `${baseName} (Copy ${suffix})`;
      suffix += 1;
    }

    const copy = await db.createDoc(doctype.Agent, {
      ...rest,
      agent_name: candidateName,
    });
    return copy as AgentDoc;
  } catch (error) {
    handleFrappeError(error, `Error duplicating agent ${name}`);
  }
}

type AgentMcpServerChildRow = {
  name?: string;
  mcp_server: string;
  enabled?: 0 | 1 | boolean;
  server_url?: string;
  tool_count?: number;
  server_name?: string;
  description?: string;
};

function toMcpEnabledFlag(value: 0 | 1 | boolean | undefined): 0 | 1 {
  return value === 1 || value === true ? 1 : 0;
}

/**
 * Link a knowledge source to an agent (persists immediately).
 */
export async function linkKnowledgeToAgent(
  agentName: string,
  knowledgeSource: string,
  defaults?: Partial<AgentKnowledgeRow>,
): Promise<AgentKnowledgeRow> {
  const agent = await getAgent(agentName);
  const existing = agent.agent_knowledge || [];

  const alreadyLinked = existing.some((row) => row.knowledge_source === knowledgeSource);
  if (alreadyLinked) {
    const linked = existing.find((row) => row.knowledge_source === knowledgeSource)!;
    return {
      name: linked.name,
      knowledge_source: linked.knowledge_source,
      mode: linked.mode || 'Optional',
      priority: linked.priority ?? 0,
      max_chunks: linked.max_chunks ?? 5,
      token_budget: linked.token_budget ?? 2000,
      description: linked.description || undefined,
    };
  }

  const newRow = {
    knowledge_source: knowledgeSource,
    mode: defaults?.mode || 'Optional',
    priority: defaults?.priority ?? 0,
    max_chunks: defaults?.max_chunks ?? 5,
    token_budget: defaults?.token_budget ?? 2000,
    description: defaults?.description || '',
  };

  const updated = await updateAgent(agentName, {
    agent_knowledge: [
      ...existing.map((row) => ({
        ...(row.name ? { name: row.name } : {}),
        knowledge_source: row.knowledge_source,
        mode: row.mode || 'Optional',
        priority: row.priority ?? 0,
        max_chunks: row.max_chunks ?? 5,
        token_budget: row.token_budget ?? 2000,
        description: row.description || '',
      })),
      newRow,
    ],
  });

  const linkedRow = (updated.agent_knowledge || []).find(
    (row) => row.knowledge_source === knowledgeSource,
  );

  return {
    name: linkedRow?.name,
    knowledge_source: knowledgeSource,
    mode: newRow.mode as 'Mandatory' | 'Optional',
    priority: newRow.priority,
    max_chunks: newRow.max_chunks,
    token_budget: newRow.token_budget,
    description: newRow.description || undefined,
  };
}

/**
 * Link an MCP server to an agent (persists immediately).
 */
export async function linkMcpServerToAgent(
  agentName: string,
  mcpServerName: string,
): Promise<MCPServerRef> {
  const agent = await getAgent(agentName);
  const existing = (agent.agent_mcp_server || []) as AgentMcpServerChildRow[];

  const alreadyLinked = existing.some((row) => row.mcp_server === mcpServerName);
  if (alreadyLinked) {
    const linked = existing.find((row) => row.mcp_server === mcpServerName)!;
    const mcpServerDoc = await getMCPServer(mcpServerName);
    return {
      name: linked.name || '',
      mcp_server: mcpServerName,
      server_name: mcpServerDoc.server_name || mcpServerName,
      description: mcpServerDoc.description || linked.description,
      server_url: mcpServerDoc.server_url || linked.server_url || '',
      enabled: toMcpEnabledFlag(linked.enabled),
      mcp_enabled: mcpServerDoc.enabled === 1 ? 1 : 0,
      tool_count: linked.tool_count || 0,
    };
  }

  const updated = await updateAgent(agentName, {
    agent_mcp_server: [
      ...existing.map((row) => ({
        ...(row.name ? { name: row.name } : {}),
        mcp_server: row.mcp_server,
        enabled: toMcpEnabledFlag(row.enabled),
      })),
      { mcp_server: mcpServerName, enabled: 1 as const },
    ],
  });

  const linkedRow = ((updated.agent_mcp_server || []) as AgentMcpServerChildRow[]).find(
    (row) => row.mcp_server === mcpServerName,
  );

  const mcpServerDoc = await getMCPServer(mcpServerName);
  return {
    name: linkedRow?.name || '',
    mcp_server: mcpServerName,
    server_name: mcpServerDoc.server_name || mcpServerName,
    description: mcpServerDoc.description,
    server_url: mcpServerDoc.server_url || '',
    enabled: 1,
    mcp_enabled: mcpServerDoc.enabled === 1 ? 1 : 0,
    tool_count: linkedRow?.tool_count || 0,
  };
}

/**
 * Model selector item (agent as model)
 */
export interface AgentModelItem {
  id: string;
  name: string;
  providerBrand: string;
  providerBrandLabel: string;
  model?: string;
  agent_color?: string | null;
  description?: string | null;
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
 * Parameters for running an agent test
 */
export interface RunAgentTestParams {
  agent_name: string;
  prompt: string;
  provider: string;
  model: string;
  now?: boolean;
}

/**
 * Response from running an agent test
 */
export interface RunAgentTestResponse {
  message?: {
    success?: boolean;
    response?: string;
    structured?: unknown;
    provider?: string;
    agent_run_id?: string;
    conversation_id?: string;
    session_id?: string;
    queued?: boolean;
    status?: string;
    sequence?: number;
  };
}

/**
 * Run an agent test
 */
export async function runAgentTest(params: RunAgentTestParams): Promise<RunAgentTestResponse> {
  try {
    const payload: Record<string, unknown> = {
      agent_name: params.agent_name,
      prompt: params.prompt,
      provider: params.provider,
      model: params.model,
    };
    if (params.now !== undefined) {
      payload.now = params.now;
    }
    const result = await call.post('huf.ai.agent_integration.run_agent_sync', payload);
    return result as RunAgentTestResponse;
  } catch (error) {
    handleFrappeError(error, 'Error running agent test');
  }
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
      filters: filters.length > 0 ? (filters as Filter<Record<string, unknown>>[]) : undefined,
      limit: limit + 1, // Fetch one extra to check if there's more
      ...(start > 0 && { limit_start: start }), // Only include if start > 0
      orderBy: { field: 'modified', order: 'desc' },
    });

    // Map agents to model format
    const mappedModels: AgentModelItem[] = (agents as Array<Record<string, string>>).map((agent) => ({
      id: agent.name,
      name: agent.agent_name || agent.name,
      providerBrand: agent.provider_brand || 'other',
      providerBrandLabel: getBrandLabel(agent.provider_brand),
      model: agent.model || '',
      agent_color: agent.agent_color || null,
      description: agent.description || null,
    }));

    const hasMore = mappedModels.length > limit;
    const items = hasMore ? mappedModels.slice(0, limit) : mappedModels;

    const total = await fetchPaginatedCount(page, items.length, doctype.Agent, filters);

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

export interface CacheableModelsResponse {
  supported: boolean;
  alternatives: string[];
}

/**
 * Check if a provider/model combination supports prompt caching
 */
export async function checkCacheableModels(
  provider?: string,
  model?: string
): Promise<CacheableModelsResponse> {
  if (!provider) {
    return { supported: false, alternatives: [] };
  }
  try {
    const response = await call.get('huf.huf.doctype.agent.agent.get_cacheable_models', {
      provider,
      model: model || undefined,
    });
    const data = response?.message || response;
    return {
      supported: Boolean(data?.supported),
      alternatives: Array.isArray(data?.alternatives) ? data.alternatives : [],
    };
  } catch {
    return { supported: false, alternatives: [] };
  }
}
