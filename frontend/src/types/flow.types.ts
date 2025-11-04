import { Node as ReactFlowNode, Edge as ReactFlowEdge } from 'reactflow';

export type FlowStatus = 'draft' | 'active' | 'paused' | 'error';

export type NodeType =
  | 'trigger'
  | 'action'
  | 'transform'
  | 'router'
  | 'loop'
  | 'human-in-loop'
  | 'code'
  | 'utility'
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

export type ActionType =
  | 'transform'
  | 'router'
  | 'human-in-loop'
  | 'loop'
  | 'code'
  | 'utility-email'
  | 'utility-file'
  | 'utility-date'
  | 'utility-webhook'
  | 'utility-http';

export type UtilityType =
  | 'email'
  | 'file'
  | 'date'
  | 'webhook'
  | 'http';

export interface WebhookTriggerConfig {
  type: 'webhook';
  url?: string;
  apiKey?: string;
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

export interface TransformActionConfig {
  type: 'transform';
  transformations?: Array<{
    sourceField: string;
    targetField: string;
    operation?: 'copy' | 'map' | 'concat' | 'split';
  }>;
}

export interface RouterActionConfig {
  type: 'router';
  branches?: Array<{
    id: string;
    name: string;
    condition: string;
  }>;
}

export interface HumanInLoopActionConfig {
  type: 'human-in-loop';
  approvers?: string[];
  message?: string;
  timeout?: number;
}

export interface LoopActionConfig {
  type: 'loop';
  iterateOver?: string;
  maxIterations?: number;
}

export interface CodeActionConfig {
  type: 'code';
  language?: 'javascript' | 'python' | 'typescript';
  code?: string;
}

export interface EmailUtilityConfig {
  type: 'utility-email';
  to?: string;
  subject?: string;
  body?: string;
  template?: string;
}

export interface FileUtilityConfig {
  type: 'utility-file';
  operation?: 'read' | 'write' | 'delete';
  path?: string;
  content?: string;
}

export interface DateUtilityConfig {
  type: 'utility-date';
  operation?: 'format' | 'add' | 'subtract' | 'compare';
  format?: string;
  value?: string;
}

export interface WebhookUtilityConfig {
  type: 'utility-webhook';
  url?: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  headers?: Record<string, string>;
  body?: string;
}

export type ActionConfig =
  | TransformActionConfig
  | RouterActionConfig
  | HumanInLoopActionConfig
  | LoopActionConfig
  | CodeActionConfig
  | EmailUtilityConfig
  | FileUtilityConfig
  | DateUtilityConfig
  | WebhookUtilityConfig
  | { type: undefined };

export interface FlowNodeData {
  label: string;
  nodeType: NodeType;
  description?: string;
  icon?: string;
  configured: boolean;
  triggerConfig?: TriggerConfig;
  actionConfig?: ActionConfig;
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
