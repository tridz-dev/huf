import { Node as ReactFlowNode, Edge as ReactFlowEdge } from 'reactflow';

export type FlowStatus = 'draft' | 'active' | 'paused' | 'error';

export type NodeType =
  | 'trigger'
  | 'action'
  | 'end';

export type TriggerType =
  | 'webhook'
  | 'schedule'
  | 'doc-event';

/**
 * Value (FIELD_CONTRACT section 2): literal, `{$from}` reference, `{$template, vars}`,
 * or arrays/objects of Values. Kept loose; the schema validates it server-side.
 */
export type FlowValue = unknown;

/** `{ "$from": "<path>" }` reference (foreach.items / foreach.collect accept only this). */
export interface FlowReference {
  $from: string;
}

export type WebhookMethod = 'GET' | 'POST';

export type DocEventName =
  | 'after_insert'
  | 'on_update'
  | 'on_submit'
  | 'on_cancel'
  | 'on_trash';

export type ApproverType = 'role' | 'user';
export type ForeachItemError = 'fail' | 'skip';

/** transform.op enum (huf.ai.graph.transforms.REGISTRY). */
export type TransformOp =
  | 'select' | 'filter' | 'sort' | 'limit' | 'group_by' | 'aggregate' | 'join'
  | 'lookup' | 'batch' | 'distinct' | 'coalesce' | 'lower' | 'upper' | 'trim'
  | 'replace' | 'contains' | 'starts_with' | 'split_first' | 'regex_extract' | 'concat';

/**
 * ActionType: the canvas discriminator for action nodes. Each maps 1:1 onto a
 * graph-IR node type (see ACTION_TO_BACKEND_TYPE in flowSerializer.ts). Presets
 * (Send Email, Slack, Sheets, File, HTTP) are all 'tool-call'.
 */
export type ActionType =
  | 'agent-run'
  | 'tool-call'
  | 'router'
  | 'router-decision'
  | 'human.approval'
  | 'condition'
  | 'foreach'
  | 'validate'
  | 'transform'
  | 'state-get'
  | 'state-set'
  | 'state-delete'
  | 'doc-create';

// ─── Trigger configs (field names == graph-IR config keys) ────────────

export interface WebhookTriggerConfig {
  type: 'webhook';
  method?: WebhookMethod;
  /** 8-256 chars; receiver compares the presented key to this. */
  secret?: string;
}

export interface ScheduleTriggerConfig {
  type: 'schedule';
  /** 5-part cron, system time. */
  cron?: string;
}

export interface DocEventTriggerConfig {
  type: 'doc-event';
  doctype?: string;
  event?: DocEventName;
}

export type TriggerConfig =
  | WebhookTriggerConfig
  | ScheduleTriggerConfig
  | DocEventTriggerConfig
  | { type: undefined };

// ─── Action configs ───────────────────────────────────────────────────
// Routing fields (next, on_error, condition on_true/on_false, router options/default,
// approve_next/reject_next/timeout_next, foreach body) are NOT config
// here: they are derived from canvas edges on every save (see FlowEdgeRoute).

export interface AgentRunActionConfig {
  type: 'agent-run';
  agent?: string;
  prompt?: string;
  prompt_bindings?: Record<string, FlowValue>;
}

export interface ToolCallActionConfig {
  type: 'tool-call';
  tool_id?: string;
  input?: Record<string, FlowValue>;
  timeout_ms?: number;
  approved?: boolean;
}

export interface RouterLlmActionConfig {
  type: 'router';
  prompt?: string;
  /** AI Model record name; absent = the provider default. */
  model?: string;
  /**
   * Fallback target node id. Kept only while it is still a routed target of this
   * node; otherwise the serializer falls back to the first option target.
   */
  default?: string;
}

export interface RouterDecisionActionConfig {
  type: 'router-decision';
  policy?: string;
  default?: string;
}

export interface HumanApprovalActionConfig {
  type: 'human.approval';
  message?: string;
  approver_type?: ApproverType;
  approver_role?: string;
  approver_users?: string[];
  timeout_ms?: number;
}

export interface ConditionActionConfig {
  type: 'condition';
  /** Restricted Python subset, subscripts not attributes: input['amount'] > 100 */
  expression?: string;
}

export interface ForeachActionConfig {
  type: 'foreach';
  items?: FlowReference;
  max_iterations?: number;
  on_item_error?: ForeachItemError;
  collect?: FlowReference;
  item_var?: string;
  index_var?: string;
}

export interface ValidateAssertion {
  expression: string;
  code: string;
  message: string;
}

export interface ValidateActionConfig {
  type: 'validate';
  assertions?: ValidateAssertion[];
}

export interface TransformActionConfig {
  type: 'transform';
  op?: TransformOp;
  input?: Record<string, FlowValue>;
}

export interface StateGetActionConfig {
  type: 'state-get';
  key?: FlowValue;
  default?: FlowValue;
}

export interface StateSetActionConfig {
  type: 'state-set';
  key?: FlowValue;
  value?: FlowValue;
  ttl_seconds?: FlowValue;
}

export interface StateDeleteActionConfig {
  type: 'state-delete';
  key?: FlowValue;
}

export interface DocCreateActionConfig {
  type: 'doc-create';
  doctype?: string;
  fields?: Record<string, FlowValue>;
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
  | RouterLlmActionConfig
  | RouterDecisionActionConfig
  | HumanApprovalActionConfig
  | ConditionActionConfig
  | ForeachActionConfig
  | ValidateActionConfig
  | TransformActionConfig
  | StateGetActionConfig
  | StateSetActionConfig
  | StateDeleteActionConfig
  | DocCreateActionConfig
  | UnknownActionConfig
  | { type: undefined };

/** End node (graph-IR `output`): `value` is a Value; there is never a `next`. */
export interface EndConfig {
  value?: FlowValue;
}

// ─── Edges ────────────────────────────────────────────────────────────

/**
 * What a canvas edge means. It is also the React Flow `sourceHandle` id for every route
 * except 'next' (default handle, sourceHandle undefined).
 *  next      -> node.next
 *  error     -> node.on_error
 *  true/false-> condition on_true / on_false
 *  option    -> router options[] (label = edge.label)
 *  default   -> router default when it is not also an option target
 *  approve/reject/timeout -> human.approval approve_next / reject_next / timeout_next
 *  body      -> foreach body (edge to the first node of a chain; chain follows `next`)
 *  (foreach "done" edge is the plain 'next' route)
 */
export type FlowEdgeRoute =
  | 'next' | 'error' | 'true' | 'false' | 'option' | 'default'
  | 'approve' | 'reject' | 'timeout' | 'body';

export interface FlowEdgeData {
  route?: FlowEdgeRoute;
}

export interface FlowNodeData {
  label: string;
  nodeType: NodeType;
  description?: string;
  icon?: string;
  configured: boolean;
  triggerConfig?: TriggerConfig;
  actionConfig?: ActionConfig;
  /** End nodes only. */
  endConfig?: EndConfig;
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
