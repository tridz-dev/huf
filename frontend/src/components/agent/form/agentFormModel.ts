/**
 * Agent form model: form defaults, doc <-> form mapping, the five-tab map and the
 * section save payloads. Pure data, no React.
 */
import type { AgentDoc, AgentToolFunctionRef, AgentKnowledgeRow, AgentPermissionUserRow, AgentPermissionRoleRow } from '@/types/agent.types';
import type { AgentSkillRow } from '@/types/skill.types';
import type { MCPServerRef } from '@/services/mcpApi';
import { DESKTOP_ACCESS_DOC_FIELDS, type AgentConfigSection } from '@/services/agentApi';
import { toDesktopAccessLevel, type AgentFormValues } from '../types';

export type AgentToolRow = { tool?: string | null };
export type AgentMcpServerRow = {
  name?: string | null;
  mcp_server: string;
  server_url?: string | null;
  enabled?: 0 | 1 | boolean;
  tool_count?: number | null;
  server_name?: string | null;
  description?: string | null;
};

export type AgentUpdatePayload = Omit<Partial<AgentDoc>, 'agent_tool'> & {
  agent_tool: Array<{ tool: string }>;
};

export function normalizeFlag(value: boolean | number | undefined): 0 | 1 {
  return value === true || value === 1 ? 1 : 0;
}

export function mapAgentDocToFormValues(agent: Partial<AgentDoc>): AgentFormValues {
  return {
    agent_name: agent.agent_name || '',
    agent_modality: (agent.agent_modality as AgentFormValues['agent_modality']) || 'Both',
    provider: agent.provider || '',
    model: agent.model || '',
    temperature: agent.temperature ?? 1,
    top_p: agent.top_p ?? 1,
    disabled: agent.disabled === 1,
    allow_chat: agent.allow_chat === 1,
    persist_conversation: agent.persist_conversation === 1,
    persist_user_history: agent.persist_user_history === 1,
    enable_multi_run: agent.enable_multi_run === 1,
    run_immediately: agent.run_immediately === 1,
    description: agent.description || '',
    instructions: agent.instructions || '',
    starter_prompts: (agent.starter_prompts || []).map((row) => ({
      name: row.name,
      prompt_text: row.prompt_text || '',
    })),
    default_plan: agent.default_plan || [],
    prompt_mode: agent.prompt_mode || 'Local',
    agent_prompt: agent.agent_prompt || '',
    prompt_version_locked: agent.prompt_version_locked === 1,
    template_version_at_attach:
      agent.template_version_at_attach !== undefined ? agent.template_version_at_attach : undefined,
    allow_all_users: !!agent.allow_all_users,
    allow_guest: !!agent.allow_guest,
    allowed_users: (agent.allowed_users || []).map((row) => row.user).filter(Boolean),
    allowed_roles: (agent.allowed_roles || []).map((row) => row.role).filter(Boolean),
    copied_from_prompt: agent.copied_from_prompt ?? undefined,
    enable_prompt_caching: agent.enable_prompt_caching === 1,
    cache_control_type: agent.cache_control_type || '',
    cache_system_message: agent.cache_system_message === 1,
    cache_conversation_history: agent.cache_conversation_history === 1,
    prompt_cache_mode: (agent.prompt_cache_mode as AgentFormValues['prompt_cache_mode']) || 'Auto',
    context_strategy: agent.context_strategy || undefined,
    summary_model: agent.summary_model || undefined,
    summary_ratio: agent.summary_ratio !== undefined && agent.summary_ratio !== null ? agent.summary_ratio : undefined,
    summary_prompt_mode: agent.summary_prompt_mode || 'Local',
    summary_prompt_template: agent.summary_prompt_template || '',
    summary_prompt_version_locked: agent.summary_prompt_version_locked === 1,
    summary_template_version_at_attach: agent.summary_template_version_at_attach !== undefined ? agent.summary_template_version_at_attach : undefined,
    summary_prompt: agent.summary_prompt || '',
    history_limit: agent.history_limit !== undefined && agent.history_limit !== null ? agent.history_limit : undefined,
    max_knowledge_tokens:
      agent.max_knowledge_tokens !== undefined && agent.max_knowledge_tokens !== null ? agent.max_knowledge_tokens : undefined,
    max_turns: agent.max_turns !== undefined && agent.max_turns !== null ? agent.max_turns : undefined,
    max_context_chars:
      agent.max_context_chars !== undefined && agent.max_context_chars !== null ? agent.max_context_chars : undefined,
    desktop_access_cli: toDesktopAccessLevel(agent.desktop_access_cli),
    desktop_access_files: toDesktopAccessLevel(agent.desktop_access_files),
    desktop_access_skills: toDesktopAccessLevel(agent.desktop_access_skills),
    desktop_access_local_mcp: toDesktopAccessLevel(agent.desktop_access_local_mcp),
    desktop_access_browser: toDesktopAccessLevel(agent.desktop_access_browser),
    desktop_access_installs: toDesktopAccessLevel(agent.desktop_access_installs),
    desktop_access_processes: toDesktopAccessLevel(agent.desktop_access_processes),
    allow_remote_desktop: agent.allow_remote_desktop === 1,
    enable_conversation_data: agent.enable_conversation_data === 1,
    inject_conversation_data: agent.inject_conversation_data === 1,
    conversation_data_api_permission: agent.conversation_data_api_permission || '',
    autonaming_of_conversation_title: agent.autonaming_of_conversation_title === 1,
    enable_memory: agent.enable_memory === 1,
    memory_policy: agent.memory_policy || '',
    enable_memory_search_tool: agent.enable_memory_search_tool !== undefined ? agent.enable_memory_search_tool === 1 : true,
    enable_memory_write_tool: agent.enable_memory_write_tool !== undefined ? agent.enable_memory_write_tool === 1 : true,
    reasoning_mode: (agent.reasoning_mode as AgentFormValues['reasoning_mode']) || 'Auto',
    reasoning_effort: (agent.reasoning_effort as AgentFormValues['reasoning_effort']) || 'Auto',
    reasoning_budget_tokens: agent.reasoning_budget_tokens !== undefined && agent.reasoning_budget_tokens !== null ? agent.reasoning_budget_tokens : undefined,
    reasoning_summary: (agent.reasoning_summary as AgentFormValues['reasoning_summary']) || 'None',
    agent_color: agent.agent_color?.trim() || '',
    show_tool_execution_details: agent.show_tool_execution_details === 1,
    agent_skill: (agent.agent_skill ?? []) as AgentFormValues['agent_skill'],
    voice_enabled: agent.voice_enabled === 1,
    voice_engine: agent.voice_engine || undefined,
    voice_config: agent.voice_config || '{}',
    voice_greeting: agent.voice_greeting || '',
    image_generation_model: agent.image_generation_model || undefined,
    tts_model: agent.tts_model || undefined,
    tts_voice: agent.tts_voice || '',
    stt_model: agent.stt_model || undefined,
    embed_enabled: agent.embed_enabled === 1,
    publishable_key: agent.publishable_key || '',
    allowed_origins: agent.allowed_origins || '',
    allow_file_upload: agent.allow_file_upload === 1,
    enable_ocr: agent.enable_ocr === 1,
    max_upload_size_mb:
      agent.max_upload_size_mb ? agent.max_upload_size_mb : 25,
    allow_code_execution: agent.allow_code_execution === 1,
    execution_profile: agent.execution_profile || undefined,
    execution_shared_dir_limit_mb:
      agent.execution_shared_dir_limit_mb ? agent.execution_shared_dir_limit_mb : undefined,
    allow_ssh: agent.allow_ssh === 1,
    ssh_connections: (agent.ssh_connections || []).map((row) => row.ssh_connection).filter(Boolean),
    allow_ask_user: agent.allow_ask_user === 1,
    allow_rich_elements: agent.allow_rich_elements === 1,
    allow_document_artifacts: agent.allow_document_artifacts === 1,
  };
}

export const DEFAULT_FORM_VALUES: AgentFormValues = {
  agent_name: '',
  agent_modality: 'Both',
  provider: '',
  model: '',
  temperature: 1,
  top_p: 1,
  disabled: false,
  allow_chat: true,
  persist_conversation: true,
  persist_user_history: true,
  enable_multi_run: false,
  run_immediately: true,
  description: '',
  instructions: '',
  starter_prompts: [],
  default_plan: [],
  prompt_mode: "Local",
  agent_prompt: '',
  prompt_version_locked: false,
  template_version_at_attach: undefined,
  allow_all_users: false,
  allow_guest: false,
  allowed_users: [],
  allowed_roles: [],
  enable_prompt_caching: false,
  cache_control_type: "",
  cache_system_message: false,
  cache_conversation_history: false,
  prompt_cache_mode: 'Auto',
  context_strategy: undefined,
  summary_model: undefined,
  summary_ratio: undefined,
  summary_prompt_mode: "Local",
  summary_prompt_template: '',
  summary_prompt_version_locked: false,
  summary_template_version_at_attach: undefined,
  summary_prompt: '',
  history_limit: undefined,
  max_knowledge_tokens: undefined,
  max_turns: undefined,
  max_context_chars: undefined,
  desktop_access_cli: 'allowed',
  desktop_access_files: 'allowed',
  desktop_access_skills: 'allowed',
  desktop_access_local_mcp: 'allowed',
  desktop_access_browser: 'allowed',
  desktop_access_installs: 'allowed',
  desktop_access_processes: 'allowed',
  allow_remote_desktop: false,
  enable_conversation_data: false,
  inject_conversation_data: true,
  conversation_data_api_permission: '',
  autonaming_of_conversation_title: true,
  enable_memory: false,
  memory_policy: '',
  enable_memory_search_tool: true,
  enable_memory_write_tool: true,
  reasoning_mode: 'Auto',
  reasoning_effort: 'Auto',
  reasoning_budget_tokens: undefined,
  reasoning_summary: 'None',
  agent_color: '',
  show_tool_execution_details: true,
  voice_enabled: false,
  voice_engine: undefined,
  voice_config: '{}',
  voice_greeting: '',
  image_generation_model: undefined,
  tts_model: undefined,
  tts_voice: '',
  stt_model: undefined,
  embed_enabled: false,
  publishable_key: '',
  allowed_origins: '',
  allow_file_upload: false,
  enable_ocr: false,
  max_upload_size_mb: 25,
  allow_code_execution: false,
  execution_profile: undefined,
  execution_shared_dir_limit_mb: undefined,
  allow_ssh: false,
  ssh_connections: [],
  allow_ask_user: false,
  allow_rich_elements: false,
  allow_document_artifacts: false,
  agent_skill: [],
};

/** Scalar Agent fields from form values, in Frappe doc format (0/1 flags). Child tables are added by the caller. */
export function formValuesToDoc(values: AgentFormValues): Record<string, unknown> {
  return {
  agent_name: values.agent_name,
  agent_modality: values.agent_modality,
  provider: values.provider,
  model: values.model,
  temperature: values.temperature,
  top_p: values.top_p,
  disabled: values.disabled ? 1 : 0,
  allow_chat: values.allow_chat ? 1 : 0,
  persist_conversation: values.persist_conversation ? 1 : 0,
  persist_user_history: values.persist_user_history ? 1 : 0,
  enable_multi_run: values.enable_multi_run ? 1 : 0,
  run_immediately: values.run_immediately ? 1 : 0,
  description: values.description || '',
  instructions: values.instructions,
  starter_prompts: (values.starter_prompts || [])
    .filter((row) => row.prompt_text?.trim())
    .map((row) => ({ prompt_text: row.prompt_text.trim() })),
  default_plan: values.default_plan || [],
  prompt_mode: values.prompt_mode || 'Local',
  agent_prompt: values.agent_prompt || '',
  prompt_version_locked: values.prompt_version_locked ? 1 : 0,
  template_version_at_attach: values.template_version_at_attach !== undefined ? values.template_version_at_attach : undefined,
  allow_all_users: values.allow_all_users,
  allow_guest: values.allow_guest,
  allowed_users: (values.allowed_users || []).map((user) => ({ user })) as AgentPermissionUserRow[],
  allowed_roles: (values.allowed_roles || []).map((role) => ({ role })) as AgentPermissionRoleRow[],
  enable_prompt_caching: values.enable_prompt_caching ? 1 : 0,
  cache_control_type: values.cache_control_type || '',
  cache_system_message: values.cache_system_message ? 1 : 0,
  cache_conversation_history: values.cache_conversation_history ? 1 : 0,
  prompt_cache_mode: values.prompt_cache_mode || 'Auto',
  context_strategy: values.context_strategy || undefined,
  summary_model: values.summary_model || undefined,
  summary_ratio: values.summary_ratio !== undefined ? values.summary_ratio : undefined,
  summary_prompt_mode: values.summary_prompt_mode || 'Local',
  summary_prompt_template: values.summary_prompt_template || '',
  summary_prompt_version_locked: values.summary_prompt_version_locked ? 1 : 0,
  summary_template_version_at_attach: values.summary_template_version_at_attach !== undefined ? values.summary_template_version_at_attach : undefined,
  summary_prompt: values.summary_prompt || '',
  history_limit: values.history_limit !== undefined ? values.history_limit : undefined,
  max_knowledge_tokens: values.max_knowledge_tokens !== undefined ? values.max_knowledge_tokens : undefined,
  max_turns: values.max_turns !== undefined ? values.max_turns : undefined,
  max_context_chars: values.max_context_chars !== undefined ? values.max_context_chars : undefined,
  desktop_access_cli: values.desktop_access_cli ?? 'allowed',
  desktop_access_files: values.desktop_access_files ?? 'allowed',
  desktop_access_skills: values.desktop_access_skills ?? 'allowed',
  desktop_access_local_mcp: values.desktop_access_local_mcp ?? 'allowed',
  desktop_access_browser: values.desktop_access_browser ?? 'allowed',
  desktop_access_installs: values.desktop_access_installs ?? 'allowed',
  desktop_access_processes: values.desktop_access_processes ?? 'allowed',
  allow_remote_desktop: values.allow_remote_desktop ? 1 : 0,
  enable_conversation_data: values.enable_conversation_data ? 1 : 0,
  inject_conversation_data: values.inject_conversation_data ? 1 : 0,
  conversation_data_api_permission: values.conversation_data_api_permission || undefined,
  autonaming_of_conversation_title: values.autonaming_of_conversation_title ? 1 : 0,
  enable_memory: values.enable_memory ? 1 : 0,
  memory_policy: values.memory_policy || undefined,
  enable_memory_search_tool: values.enable_memory_search_tool ? 1 : 0,
  enable_memory_write_tool: values.enable_memory_write_tool ? 1 : 0,
  reasoning_mode: values.reasoning_mode || 'Auto',
  reasoning_effort: values.reasoning_effort || 'Auto',
  reasoning_budget_tokens: values.reasoning_budget_tokens !== undefined ? values.reasoning_budget_tokens : undefined,
  reasoning_summary: values.reasoning_summary || 'None',
  agent_color: values.agent_color?.trim() || undefined,
  show_tool_execution_details: values.show_tool_execution_details ? 1 : 0,

  voice_enabled: values.voice_enabled ? 1 : 0,
  voice_engine: values.voice_engine || undefined,
  voice_config: values.voice_config || '{}',
  voice_greeting: values.voice_greeting || '',
  image_generation_model: values.image_generation_model || undefined,
  tts_model: values.tts_model || undefined,
  tts_voice: values.tts_voice || undefined,
  stt_model: values.stt_model || undefined,
  embed_enabled: values.embed_enabled ? 1 : 0,
  publishable_key: values.publishable_key || undefined,
  allowed_origins: values.allowed_origins || '',
  allow_file_upload: values.allow_file_upload ? 1 : 0,
  enable_ocr: values.enable_ocr ? 1 : 0,
  max_upload_size_mb: values.max_upload_size_mb !== undefined ? values.max_upload_size_mb : undefined,
  allow_code_execution: values.allow_code_execution ? 1 : 0,
  execution_profile: values.execution_profile || undefined,
  execution_shared_dir_limit_mb: values.execution_shared_dir_limit_mb !== undefined ? values.execution_shared_dir_limit_mb : undefined,
  allow_ssh: values.allow_ssh ? 1 : 0,
  ssh_connections: (values.ssh_connections || []).map((connectionName) => ({
    ssh_connection: connectionName,
  })),
  allow_ask_user: values.allow_ask_user ? 1 : 0,
  allow_rich_elements: values.allow_rich_elements ? 1 : 0,
  allow_document_artifacts: values.allow_document_artifacts ? 1 : 0,
  };
}

/** Child-table rows in Frappe doc format. */
export function toolRows(tools: AgentToolFunctionRef[]) {
  return tools.map((tool) => ({ tool: tool.name }));
}
export function mcpRows(servers: MCPServerRef[]) {
  return servers.map((s) => ({ mcp_server: s.mcp_server, enabled: normalizeFlag(s.enabled) }));
}
export function knowledgeRows(rows: AgentKnowledgeRow[]) {
  return rows.map((ks) => ({
    ...(ks.name ? { name: ks.name } : {}),
    knowledge_source: ks.knowledge_source,
    mode: ks.mode,
    priority: ks.priority,
    max_chunks: ks.max_chunks,
    token_budget: ks.token_budget,
    description: ks.description || '',
  }));
}
export function skillRows(rows: AgentSkillRow[]) {
  return rows.map((skill) => ({
    ...(skill.name ? { name: skill.name } : {}),
    skill: skill.skill,
    mode: skill.mode,
    auto_load: normalizeFlag(skill.auto_load),
    priority: skill.priority ?? 0,
    description: skill.description || '',
  }));
}

export function toKnowledgeRows(items: Array<Partial<AgentKnowledgeRow>> | undefined): AgentKnowledgeRow[] {
  return (items || []).map((item) => ({
    name: item.name,
    knowledge_source: item.knowledge_source as string,
    mode: item.mode || 'Optional',
    priority: item.priority ?? 0,
    max_chunks: item.max_chunks ?? 5,
    token_budget: item.token_budget ?? 2000,
    description: item.description || undefined,
  })) as AgentKnowledgeRow[];
}

export function toSkillRows(items: AgentDoc['agent_skill'] | undefined): AgentSkillRow[] {
  return ((items || []) as AgentSkillRow[]).map((item) => ({
    name: item.name,
    skill: item.skill,
    mode: item.mode || 'Optional',
    auto_load: normalizeFlag(item.auto_load),
    priority: item.priority ?? 0,
    description: item.description || undefined,
  })) as AgentSkillRow[];
}

export function toMcpRefs(items: AgentMcpServerRow[] | undefined): MCPServerRef[] {
  return (items || []).map((item) => ({
    name: item.name || '',
    mcp_server: item.mcp_server,
    server_url: item.server_url || '',
    enabled: normalizeFlag(item.enabled),
    tool_count: item.tool_count || 0,
    server_name: item.server_name ?? undefined,
    description: item.description ?? undefined,
  }));
}

/** Form fields owned by each backend section (config_api AGENT_SECTIONS). Child-table sections have no form fields. */
export const SECTION_FIELDS: Record<AgentConfigSection, readonly (keyof AgentFormValues)[]> = {
  general: ['agent_name', 'agent_modality', 'provider', 'model', 'temperature', 'top_p', 'disabled', 'run_immediately', 'description', 'instructions', 'starter_prompts', 'enable_prompt_caching', 'cache_control_type', 'cache_system_message', 'cache_conversation_history', 'prompt_cache_mode', 'prompt_mode', 'agent_prompt', 'prompt_version_locked', 'template_version_at_attach'],
  behavior: ['allow_chat', 'persist_conversation', 'persist_user_history', 'enable_multi_run', 'default_plan', 'allow_ask_user', 'allow_rich_elements', 'allow_document_artifacts'],
  voice: ['voice_enabled', 'voice_engine', 'voice_config', 'voice_greeting', 'tts_model', 'tts_voice', 'stt_model'],
  embed: ['embed_enabled', 'publishable_key', 'allowed_origins'],
  permissions: [
    'allow_all_users', 'allow_guest', 'allowed_users', 'allowed_roles', 'enable_conversation_data', 'conversation_data_api_permission',
    'allow_code_execution', 'execution_profile', 'execution_shared_dir_limit_mb', 'allow_ssh', 'ssh_connections',
    ...(DESKTOP_ACCESS_DOC_FIELDS as readonly (keyof AgentFormValues)[]),
  ],
  advanced: [
    'context_strategy', 'summary_model', 'summary_ratio', 'summary_prompt_mode', 'summary_prompt_template', 'summary_prompt_version_locked',
    'summary_template_version_at_attach', 'summary_prompt', 'history_limit', 'max_knowledge_tokens', 'max_turns', 'max_context_chars',
    'enable_conversation_data', 'inject_conversation_data', 'autonaming_of_conversation_title', 'enable_memory', 'memory_policy',
    'enable_memory_search_tool', 'enable_memory_write_tool', 'reasoning_mode', 'reasoning_effort', 'reasoning_budget_tokens', 'reasoning_summary',
    'agent_color', 'show_tool_execution_details', 'image_generation_model', 'allow_file_upload', 'enable_ocr', 'max_upload_size_mb',
  ],
  tools: [],
  knowledge: [],
  skills: [],
};

export const ALL_SECTIONS = Object.keys(SECTION_FIELDS) as AgentConfigSection[];
/** Order matters: general first so a rename or disable lands before the rest. */
export const SAVE_ORDER: AgentConfigSection[] = ['general', 'behavior', 'voice', 'embed', 'tools', 'knowledge', 'skills', 'permissions', 'advanced'];

export const SECTION_LABEL: Record<AgentConfigSection, string> = {
  general: 'Setup', behavior: 'Channels', voice: 'Channels', embed: 'Channels', tools: 'Abilities', knowledge: 'Abilities',
  skills: 'Abilities', permissions: 'Access', advanced: 'Advanced',
};

/** The five tabs. */
export const TABS = [
  { key: 'setup', label: 'Setup' },
  { key: 'abilities', label: 'Abilities' },
  { key: 'channels', label: 'Channels' },
  { key: 'access', label: 'Access' },
  { key: 'advanced', label: 'Advanced' },
] as const;
export type TabKey = (typeof TABS)[number]['key'];

/** Old 12-tab hashes and `showTab` navigation state map onto the five tabs. */
const LEGACY_TABS: Record<string, TabKey> = {
  general: 'setup', behavior: 'channels', voice: 'channels', embed: 'channels', triggers: 'channels',
  tools: 'abilities', knowledge: 'abilities', skills: 'abilities', procedures: 'abilities', permissions: 'access',
};
export function resolveTab(name: string | undefined | null): TabKey | undefined {
  if (!name) return undefined;
  if (TABS.some((t) => t.key === name)) return name as TabKey;
  return LEGACY_TABS[name];
}

const TAB_OF_SECTION: Record<AgentConfigSection, TabKey> = {
  general: 'setup', behavior: 'channels', voice: 'channels', embed: 'channels', tools: 'abilities', knowledge: 'abilities',
  skills: 'abilities', permissions: 'access', advanced: 'advanced',
};
/** Which tab shows a given form field (used to focus the tab holding the first error). */
export function tabForField(field: string): TabKey {
  if (field === 'conversation_data_api_permission') return 'access';
  for (const section of SAVE_ORDER) {
    if ((SECTION_FIELDS[section] as readonly string[]).includes(field)) return TAB_OF_SECTION[section];
  }
  return 'setup';
}

export const isDesktopField = (field: string) => (DESKTOP_ACCESS_DOC_FIELDS as readonly string[]).includes(field);

/** Stable signature of a value, for dirty detection. */
export const sig = (v: unknown) => JSON.stringify(v ?? null);

export function pickFields(values: AgentFormValues, fields: readonly (keyof AgentFormValues)[]) {
  return Object.fromEntries(fields.map((f) => [f, values[f]]));
}
