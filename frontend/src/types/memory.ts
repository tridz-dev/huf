export interface MemoryRecord {
  name: string;
  title: string;
  record_type: string;
  scope_type: string;
  scope_key: string;
  visibility: string;
  status: string;
  summary_text: string;
  confidence: number;
  importance_score: number;
  tags: string;
  agent?: string;
  conversation?: string;
  knowledge_source?: string;
  projection_status?: string;
  modified: string;
}

export type MemoryScopeType =
  | 'Conversation'
  | 'User'
  | 'Role'
  | 'Agent'
  | 'Workspace'
  | 'Site'
  | 'Global';

export type MemoryCaptureMode = 'Manual' | 'Agent Suggested' | 'Automatic';

export type MemoryDefaultStatus = 'Draft' | 'Active';

export type MemoryInjectMode = 'Never' | 'Relevant Only' | 'Always' | 'Tool Only';

export interface MemoryPolicyDoc {
  name: string;
  owner?: string;
  creation?: string;
  modified: string;
  modified_by?: string;
  doctype?: 'Memory Policy';

  policy_name: string;
  enabled: 0 | 1;
  agent?: string | null;

  scope_type: MemoryScopeType;
  scope_key?: string | null;

  capture_mode: MemoryCaptureMode;
  learning_agent?: string | null;
  approval_required: 0 | 1;
  default_status: MemoryDefaultStatus;
  allowed_record_types?: string | null;

  inject_mode: MemoryInjectMode;
  max_records: number;
  token_budget: number;

  allow_agent_write: 0 | 1;
  allow_user_scope_write: 0 | 1;
  allow_role_scope_write: 0 | 1;
  allow_agent_scope_write: 0 | 1;
  allow_site_scope_write: 0 | 1;

  auto_promote_to_knowledge: 0 | 1;
  knowledge_source?: string | null;
  promotion_min_confidence: number;
  promotion_min_importance: number;

  ttl_days: number;
  metadata_json?: string | null;
}
