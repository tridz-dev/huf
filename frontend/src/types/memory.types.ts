import * as z from 'zod';

/**
 * Memory Record - Primary DocType for the HUF Memory System
 * Based on PRD Section 9.1
 */
export interface MemoryRecord {
  name: string;
  title: string;
  agent: string;
  agent_name?: string;
  conversation?: string;
  run?: string;
  source_type: MemorySourceType;
  producer_mode: MemoryProducerMode;
  memory_type: MemoryType;
  schema_name?: string;
  profile_name?: string;
  data_json: Record<string, unknown>;
  summary_text?: string;
  raw_context_excerpt?: string;
  scope_type: MemoryScopeType;
  scope_key: string;
  visibility: MemoryVisibility;
  status: MemoryStatus;
  confidence?: number;
  importance_score?: number;
  ttl_days?: number;
  effective_from?: string;
  effective_until?: string;
  supersedes_memory_record?: string;
  created_from_turn_count?: number;
  tags?: string[];
  metadata_json?: Record<string, unknown>;
  fts_indexed: boolean;
  vector_indexed: boolean;
  index_backend: MemoryIndexBackend;
  last_indexed_at?: string;
  last_retrieved_at?: string;
  retrieval_count: number;
  owner: string;
  creation: string;
  modified: string;
  modified_by: string;
}

/**
 * Memory Policy - Configuration DocType for memory capture
 * Based on PRD Section 9.2
 */
export interface MemoryPolicy {
  name: string;
  policy_name: string;
  enabled: boolean;
  agent: string;
  memory_profile?: string;
  capture_owner: MemoryProducerMode;
  memory_agent?: string;
  capture_stage: MemoryCaptureStage;
  capture_frequency_type: MemoryCaptureFrequency;
  capture_frequency_value?: number;
  conversation_end_strategy: ConversationEndStrategy;
  idle_timeout_minutes?: number;
  capture_prompt?: string;
  capture_schema_json?: Record<string, unknown>;
  allow_open_schema: boolean;
  require_json_schema_match: boolean;
  allow_update_existing: boolean;
  allow_merge: boolean;
  allow_append: boolean;
  min_confidence?: number;
  store_raw_payload: boolean;
  store_summary: boolean;
  enable_fts_index: boolean;
  enable_vector_index: boolean;
  vector_backend?: string;
  fts_backend?: string;
  retrieval_mode_default: MemoryRetrievalMode;
  max_items_to_inject?: number;
  max_tokens_to_inject?: number;
}

/**
 * Memory Profile - Opinionated preset for memory capture
 * Based on PRD Section 9.3
 */
export interface MemoryProfile {
  name: string;
  profile_name: string;
  description?: string;
  category: MemoryProfileCategory;
  default_schema_json?: Record<string, unknown>;
  default_capture_prompt?: string;
  recommended_model?: string;
  recommended_provider?: string;
  default_capture_stage: MemoryCaptureStage;
  default_frequency: MemoryCaptureFrequency;
  default_scope_type: MemoryScopeType;
  default_indexing_mode: MemoryIndexBackend;
  default_retrieval_mode: MemoryRetrievalMode;
  default_memory_type_mapping?: Record<string, MemoryType>;
  icon?: string;
  is_system_profile: boolean;
}

/**
 * Memory source types
 */
export type MemorySourceType = 
  | 'conversation'
  | 'run'
  | 'manual'
  | 'event'
  | 'scheduled'
  | 'imported';

/**
 * Memory producer modes - who/what produces the memory
 */
export type MemoryProducerMode = 
  | 'main_agent'
  | 'memory_agent'
  | 'post_run_llm'
  | 'rules_only'
  | 'manual';

/**
 * Memory types
 */
export type MemoryType = 
  | 'profile'
  | 'session_state'
  | 'preference'
  | 'fact'
  | 'plan'
  | 'observation'
  | 'insight'
  | 'domain_object'
  | 'custom';

/**
 * Memory scope types
 */
export type MemoryScopeType = 
  | 'conversation'
  | 'user'
  | 'agent'
  | 'namespace'
  | 'global';

/**
 * Memory visibility levels
 */
export type MemoryVisibility = 
  | 'private'
  | 'shared_with_agent'
  | 'shared_with_namespace'
  | 'global';

/**
 * Memory status
 */
export type MemoryStatus = 
  | 'active'
  | 'superseded'
  | 'archived'
  | 'expired'
  | 'error';

/**
 * Memory index backends
 */
export type MemoryIndexBackend = 
  | 'none'
  | 'sqlite_fts'
  | 'sqlite_vec'
  | 'pgvector'
  | 'custom';

/**
 * Memory capture stages
 */
export type MemoryCaptureStage = 
  | 'in_prompt'
  | 'post_response_sync'
  | 'post_response_async'
  | 'conversation_end'
  | 'scheduled';

/**
 * Memory capture frequency types
 */
export type MemoryCaptureFrequency = 
  | 'every_run'
  | 'every_n_runs'
  | 'every_n_turns'
  | 'conversation_end'
  | 'manual'
  | 'scheduled';

/**
 * Conversation end strategies
 */
export type ConversationEndStrategy = 
  | 'manual_close'
  | 'idle_timeout'
  | 'heuristic'
  | 'never';

/**
 * Memory retrieval modes
 */
export type MemoryRetrievalMode = 
  | 'inject'
  | 'tool_only'
  | 'hybrid';

/**
 * Memory profile categories
 */
export type MemoryProfileCategory = 
  | 'Programming'
  | 'Science'
  | 'Language'
  | 'Reasoning'
  | 'General'
  | 'Travel'
  | 'CRM'
  | 'Support'
  | 'Documentation'
  | 'Custom';

/**
 * Memory filters for querying records
 */
export interface MemoryFilters {
  scope_type?: MemoryScopeType;
  agent?: string;
  memory_type?: MemoryType;
  profile_name?: string;
  status?: MemoryStatus;
  tags?: string[];
  fts_indexed?: boolean;
  vector_indexed?: boolean;
  start_date?: string;
  end_date?: string;
  search_query?: string;
}

/**
 * Agent Memory Settings - Fields to add to Agent DocType
 * Based on PRD Section 10.1
 */
export interface AgentMemorySettings {
  enable_memory: boolean;
  memory_policy?: string;
  default_memory_scope_type: MemoryScopeType;
  default_memory_scope_key_template?: string;
  memory_retrieval_mode: MemoryRetrievalMode;
  memory_in_prompt_budget?: number;
  enable_memory_search_tool: boolean;
  enable_memory_write_tool: boolean;
  memory_profile?: string;
  memory_agent?: string;
  memory_run_order: 'before_main_response' | 'after_main_response' | 'background';
  memory_max_items?: number;
  memory_index_backend_default: MemoryIndexBackend;
  memory_visibility_default: MemoryVisibility;
}

/**
 * Form values for memory configuration in Agent form
 */
export const memoryFormSchema = z.object({
  enable_memory: z.boolean().default(false),
  memory_policy: z.string().optional(),
  default_memory_scope_type: z.enum(['conversation', 'user', 'agent', 'namespace', 'global']).default('conversation'),
  default_memory_scope_key_template: z.string().optional(),
  memory_retrieval_mode: z.enum(['inject', 'tool_only', 'hybrid']).default('tool_only'),
  memory_in_prompt_budget: z.number().optional(),
  enable_memory_search_tool: z.boolean().default(true),
  enable_memory_write_tool: z.boolean().default(false),
  memory_profile: z.string().optional(),
  memory_agent: z.string().optional(),
  memory_run_order: z.enum(['before_main_response', 'after_main_response', 'background']).default('after_main_response'),
  memory_max_items: z.number().optional(),
  memory_index_backend_default: z.enum(['none', 'sqlite_fts', 'sqlite_vec', 'pgvector', 'custom']).default('sqlite_fts'),
  memory_visibility_default: z.enum(['private', 'shared_with_agent', 'shared_with_namespace', 'global']).default('private'),
});

export type MemoryFormValues = z.infer<typeof memoryFormSchema>;

/**
 * Memory Record row for lists
 */
export interface MemoryRecordRow {
  name: string;
  title: string;
  agent: string;
  agent_name?: string;
  memory_type: MemoryType;
  scope_type: MemoryScopeType;
  status: MemoryStatus;
  confidence?: number;
  importance_score?: number;
  tags?: string[];
  creation: string;
  modified: string;
}

/**
 * Memory statistics for dashboards
 */
export interface MemoryStats {
  total_records: number;
  by_type: Record<MemoryType, number>;
  by_scope: Record<MemoryScopeType, number>;
  by_status: Record<MemoryStatus, number>;
  recently_created: number;
  recently_retrieved: number;
  indexed_fts: number;
  indexed_vector: number;
}

/**
 * Memory capture result
 */
export interface MemoryCaptureResult {
  success: boolean;
  records_created: number;
  records_updated: number;
  records_skipped: number;
  error_message?: string;
  latency_ms?: number;
}

/**
 * Memory retrieval result
 */
export interface MemoryRetrievalResult {
  records: MemoryRecord[];
  total_count: number;
  query_time_ms: number;
}
