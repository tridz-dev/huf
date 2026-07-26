export type SkillSourceType = 'Local' | 'Git' | 'Common Destination' | 'App Provided';
export type SkillStatus = 'Draft' | 'Active' | 'Error' | 'Disabled';
export type SkillKnowledgeMode = 'Mandatory' | 'Optional';
export type SkillPromptUsage = 'System' | 'User';

export interface SkillTool {
  name?: string;
  tool: string;
  tool_name?: string;
  description?: string;
  required?: 0 | 1 | boolean;
}

export interface SkillKnowledge {
  name?: string;
  knowledge_source: string;
  source_name?: string;
  mode: SkillKnowledgeMode;
  max_chunks?: number;
  token_budget?: number;
}

export interface SkillPrompt {
  name?: string;
  prompt: string;
  title?: string;
  usage: SkillPromptUsage;
}

export interface SkillMcpServer {
  name?: string;
  mcp_server: string;
  server_name?: string;
  enabled?: 0 | 1 | boolean;
}

export interface SkillDoc {
  name: string;
  owner: string;
  creation: string;
  modified: string;
  modified_by: string;
  docstatus: number;
  idx: number;
  doctype: 'Skill';

  skill_name: string;
  title: string;
  description?: string | null;
  skill_category?: string | null;
  version?: string | null;
  author?: string | null;
  source_type: SkillSourceType;
  source_url?: string | null;
  source_path?: string | null;
  source_ref?: string | null;
  provider_app?: string | null;
  status: SkillStatus;
  skill_icon?: string | null;
  instructions?: string | null;
  auto_load?: 0 | 1;

  skill_tools?: SkillTool[];
  skill_knowledge?: SkillKnowledge[];
  skill_prompts?: SkillPrompt[];
  skill_mcp_servers?: SkillMcpServer[];
}

export interface AgentSkillRow {
  name?: string;
  skill: string;
  skill_name?: string;
  mode: SkillKnowledgeMode;
  auto_load?: 0 | 1 | boolean;
  priority?: number;
  description?: string;
}

export interface SkillOption {
  value: string;
  label: string;
  description?: string;
}
