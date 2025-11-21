export type AIProvider = {
  name: string;
  provider_name: string;
};

export type AIModel = {
  name: string;
  model_name: string;
  provider: string;
};

export type ToolType =
  | "Get Document"
  | "Get Multiple Documents"
  | "Get List"
  | "Create Document"
  | "Create Multiple Documents"
  | "Update Document"
  | "Update Multiple Documents"
  | "Delete Document"
  | "Delete Multiple Documents"
  | "Submit Document"
  | "Cancel Document"
  | "Get Amended Document"
  | "Custom Function"
  | "App Provided"
  | "Attach File to Document"
  | "Get Report Result"
  | "Get Value"
  | "Set Value"
  | "GET"
  | "POST"
  | "Run Agent"
  | "Speech to Text";

export type AgentToolFunctionRef = {
  name: string;
  tool_name: string;
  description?: string;
  types?: ToolType;
  reference_doctype?: string;
  function_path?: string;
  provider_app?: string;
  tool_type?: string; // Link to Agent Tool Type
};

export type AgentToolType = {
  name: string;
  name1: string; // The display name of the tool type
};

export type AgentCategory = "Sales" | "Support" | "Operations" | "Marketing" | "Finance" | "HR" | "General";
export type AgentVisibility = "Private" | "Team" | "Global";
export type AgentEnvironment = "Dev" | "Prod";
export type AgentStatus = "Draft" | "Active" | "Archived";

export type ScheduledInterval = "Hourly" | "Daily" | "Weekly" | "Monthly" | "Yearly";
export type DocEventType = "before_insert" | "after_insert" | "validate" | "before_save" | "after_save" | "before_submit" | "on_submit" | "after_submit" | "on_cancel" | "before_rename" | "after_rename" | "on_trash" | "after_delete";
export type TriggerType = "Schedule" | "Doc Event" | "Webhook" | "App Event" | "Manual";

export type AgentTrigger = {
  id: string;
  trigger_type: TriggerType;
  active: boolean;

  // Schedule fields
  schedule_interval?: ScheduledInterval;
  interval_count?: number;
  last_execution?: string;
  next_execution?: string;

  // Doc Event fields
  reference_doctype?: string;
  doc_event?: DocEventType;
  condition?: string;

  // Webhook fields
  webhook_url?: string;
  webhook_slug?: string;

  // App Event fields
  app_name?: string;
  event_name?: string;

  created_at?: string;
  updated_at?: string;
};

export type Agent = {
  name: string;
  agent_name: string;
  provider: string;
  model: string;
  description?: string;
  instructions: string;
  temperature?: number;
  top_p?: number;
  disabled?: boolean;
  allow_chat?: boolean;
  persist_conversation?: boolean;
  triggers: AgentTrigger[];
  tags?: string[];
  category?: AgentCategory;
  visibility?: AgentVisibility;
  environment?: AgentEnvironment;
  status?: AgentStatus;
  tools: AgentToolFunctionRef[];
  stats?: {
    conversations: number;
    lastRunAt?: string;
    successRate?: number;
    avgCost?: number;
    avgLatencyMs?: number;
    token24h?: { input: number; output: number; total: number };
  };
  created_at?: string;
  updated_at?: string;
};

export type AgentConversation = {
  name: string;
  title: string;
  agent: string;
  session_id?: string;
  is_active: boolean;
  total_messages: number;
  last_message_at?: string;
};

export type AgentMessage = {
  name: string;
  conversation: string;
  role: "user" | "agent" | "system";
  content: string;
  created_at: string;
};

export type AgentRun = {
  name: string;
  conversation: string;
  agent: string;
  prompt: string;
  response?: string;
  status: "Started" | "Queued" | "Success" | "Failed";
  error_message?: string;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  total_cost?: number;
  latency_ms?: number;
  created_at: string;
};

/**
 * Agent document type from Frappe
 * Represents the raw Agent document structure from Frappe database
 * Based on the Agent doctype schema
 */
export interface AgentDoc {
  // Standard Frappe fields
  name: string;
  owner: string;
  creation: string;
  modified: string;
  modified_by: string;
  docstatus: number;
  idx: number;
  doctype: "Agent";

  // Agent specific fields
  agent_name: string;
  provider: string;
  model: string;
  chef?: string | null; // Chef/provider name (e.g., OpenAI, Anthropic)
  slug?: string | null; // Provider slug (e.g., openai, anthropic)
  disabled: number; // 0 or 1
  temperature: number;
  top_p: number;
  allow_chat: number; // 0 or 1
  persist_conversation: number; // 0 or 1
  is_scheduled: number; // 0 or 1
  scheduled_interval: ScheduledInterval | null;
  interval_count: number | null;
  last_execution: string | null;
  next_execution: string | null;
  reference_doctype: string | null;
  condition: string | null;
  is_doc_event: number; // 0 or 1
  doc_event: DocEventType | null;
  description?: string | null;
  instructions: string;
  agent_tool: AgentToolFunctionRef[]; // Array of agent tool references
  last_run?: string | null; // Last execution timestamp
  total_run?: number; // Total number of runs
}
