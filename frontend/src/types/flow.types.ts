import { Node as ReactFlowNode, Edge as ReactFlowEdge } from 'reactflow';
import type { BackendSettings } from '../services/flowApi';

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
  | 'human.approval'
  | 'condition'
  | 'http-request'
  | 'transform'
  | 'loop'
  | 'state-get'
  | 'state-set'
  | 'state-delete'
  | 'doc-create';

export interface WebhookTriggerConfig {
  type: 'webhook';
  url?: string;
  apiKey?: string;
  auth?: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  headers?: Record<string, string>;
  body_template?: string;
}

export interface ScheduleTriggerConfig {
  type: 'schedule';
  /** 5-field cron; mirrors the trigger saved via set_flow_trigger (FlowTriggerPanel). */
  cron?: string;
}

export interface DocEventTriggerConfig {
  type: 'doc-event';
  /** Mirror the trigger saved via set_flow_trigger (FlowTriggerPanel). */
  doctype?: string;
  event?: 'after_insert' | 'on_update' | 'on_submit' | 'on_cancel' | 'on_trash';
}

export interface AppTriggerConfig {
  type: 'app-trigger';
  integration?: AppTriggerIntegration;
  event?: string;
  config?: Record<string, unknown>;
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
  /** Set when the selected tool comes from an MCP server (list_flow_tools() source: 'mcp'); null/undefined for built-in tools. */
  mcp_server?: string | null;
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

export interface HumanApprovalActionConfig {
  type: 'human.approval';
  title?: string;
  instructions?: string;
  context_summary?: string;
  approval_type?: 'role' | 'user';
  assigned_role?: string;
  assigned_user?: string[];
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
  /** Backend transform op (see lib/flowTransformOps.ts) and its graph-IR `input` Values. */
  op?: string;
  input?: Record<string, unknown>;
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

/** state.get / state.set / state.delete — graph-IR `Value`s (literal, $from ref or $template). */
export interface StateGetActionConfig {
  type: 'state-get';
  key?: unknown;
  default?: unknown;
}

export interface StateSetActionConfig {
  type: 'state-set';
  key?: unknown;
  value?: unknown;
  ttl_seconds?: unknown;
}

export interface StateDeleteActionConfig {
  type: 'state-delete';
  key?: unknown;
}

/** doc.create — doctype must be in the site allow-list; fields are graph-IR Values. */
export interface DocCreateActionConfig {
  type: 'doc-create';
  doctype?: string;
  fields?: Record<string, unknown>;
}

/**
 * A backend node type this UI has no editor for. Kept verbatim (`backend_type` + its
 * config) so it round-trips instead of being rewritten as a tool call.
 */
export interface UnknownActionConfig {
  type: 'unknown';
  backend_type: string;
  [key: string]: unknown;
}

export type ActionConfig =
  | AgentRunActionConfig
  | ToolCallActionConfig
  | RouterActionConfig
  | HumanApprovalActionConfig
  | ConditionActionConfig
  | HttpRequestActionConfig
  | TransformActionConfig
  | LoopActionConfig
  | StateGetActionConfig
  | StateSetActionConfig
  | StateDeleteActionConfig
  | DocCreateActionConfig
  | UnknownActionConfig
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
  status?: 'idle' | 'running' | 'success' | 'error' | 'waiting';
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
  /** Engine execution settings (mirrors backend definition_json.settings) */
  settings?: BackendSettings;
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
