import { Node as ReactFlowNode, Edge as ReactFlowEdge } from 'reactflow';

export type FlowStatus = 'draft' | 'active' | 'paused' | 'error';

export type NodeType =
  | 'trigger'
  | 'action'
  | 'end';

export type TriggerType =
  | 'webhook'
  | 'schedule'
  | 'doc-event'
  | 'app-trigger';

export type AppTriggerIntegration =
  | 'gmail'
  | 'calendar'
  | 'slack'
  | 'notion'
  | 'hubspot'
  | 'sheets';

export type ScheduleIntervalType =
  | 'minutes'
  | 'hours'
  | 'days'
  | 'custom';

export type DocEventType =
  | 'save'
  | 'update'
  | 'delete'
  | 'before-save'
  | 'before-update'
  | 'before-delete';

/**
 * ActionType — only types with real backend executors.
 * Ghost types (utility-email, utility-file, utility-date, etc.) have been removed.
 */
export type ActionType =
  | 'agent-run'
  | 'tool-call'
  | 'router'
  | 'human-in-loop'
  | 'condition'
  | 'http-request'
  | 'transform'
  | 'loop';

export interface WebhookTriggerConfig {
  type: 'webhook';
  url?: string;
  apiKey?: string;
  auth?: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
}

export interface ScheduleTriggerConfig {
  type: 'schedule';
  intervalType: ScheduleIntervalType;
  interval?: number;
  cronExpression?: string;
  timezone?: string;
}

export interface DocEventTriggerConfig {
  type: 'doc-event';
  doctype?: string;
  event?: DocEventType;
}

export interface AppTriggerConfig {
  type: 'app-trigger';
  integration?: AppTriggerIntegration;
  event?: string;
  config?: Record<string, any>;
}

export type TriggerConfig =
  | WebhookTriggerConfig
  | ScheduleTriggerConfig
  | DocEventTriggerConfig
  | AppTriggerConfig
  | { type: undefined };

export interface AgentRunActionConfig {
  type: 'agent-run';
  agent_name?: string;
  prompt_template?: string;
  save_response_to_context?: string;
  inject_flow_context?: boolean;
}

export interface ToolCallActionConfig {
  type: 'tool-call';
  tool_name?: string;
  args?: Record<string, unknown>;
  save_result_to_context?: string;
  output?: {
    save_result_to_context?: string;
  };
}

export interface RouterActionConfig {
  type: 'router';
  router_agent_name?: string;
  conversation_mode?: 'flow_shared' | 'isolated';
}

export interface HumanInLoopActionConfig {
  type: 'human-in-loop';
  title?: string;
  instructions?: string;
  context_summary?: string;
  approval_type?: 'role' | 'user';
  approver_role?: string;
  approver_users?: string[];
  reference_doctype?: string;
  reference_name?: string;
  store_decision_in_context?: string;
}

/**
 * Condition (IF) node — explicit branching with True/False ports.
 * n8n-inspired: replaces opaque edge-level expression logic.
 */
export interface ConditionActionConfig {
  type: 'condition';
  expression?: string;
  true_node?: string;
  false_node?: string;
}

/**
 * HTTP Request node — makes external API calls.
 */
export interface HttpRequestActionConfig {
  type: 'http-request';
  url?: string;
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  headers?: Record<string, string>;
  body?: string;
  timeout?: number;
  save_result_to_context?: string;
}

/**
 * Transform node — data mapping between context variables.
 */
export interface TransformActionConfig {
  type: 'transform';
  transformations?: Array<{
    source_field: string;
    target_field: string;
    operation?: 'copy' | 'map' | 'template';
  }>;
}

/**
 * Loop node — iterate over an array in context.
 * Inspired by n8n's "Split In Batches" / "Loop Over Items".
 */
export interface LoopActionConfig {
  type: 'loop';
  iterate_over?: string;
  item_key?: string;
  index_key?: string;
  loop_node?: string;
  done_node?: string;
  max_iterations?: number;
}

export type ActionConfig =
  | AgentRunActionConfig
  | ToolCallActionConfig
  | RouterActionConfig
  | HumanInLoopActionConfig
  | ConditionActionConfig
  | HttpRequestActionConfig
  | TransformActionConfig
  | LoopActionConfig
  | { type: undefined };

export interface FlowEdgeData {
  edgeType?: 'always' | 'on_success' | 'on_failure' | 'expression';
  priority?: number;
  condition?: string;
  meta?: Record<string, unknown>;
}

export interface FlowNodeData {
  label: string;
  nodeType: NodeType;
  description?: string;
  icon?: string;
  configured: boolean;
  triggerConfig?: TriggerConfig;
  actionConfig?: ActionConfig;
  /** Live execution status — updated via Frappe Realtime events */
  status?: 'idle' | 'running' | 'success' | 'error';
}

export type FlowNode = ReactFlowNode<FlowNodeData>;
export type FlowEdge = ReactFlowEdge;

export interface Flow {
  id: string;
  name: string;
  description?: string;
  status: FlowStatus;
  category?: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  createdAt: Date;
  updatedAt: Date;
  version: number;
}

export interface FlowMetadata {
  id: string;
  name: string;
  description?: string;
  status: FlowStatus;
  category?: string;
  nodeCount: number;
  createdAt: Date;
  updatedAt: Date;
}
