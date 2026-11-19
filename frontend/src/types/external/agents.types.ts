/**
 * Types for external agent connections (Claude Code, Codex, other runtimes)
 * and their sessions, events and approvals.
 */

export type ExternalPolicy = 'Allow' | 'Requires Approval' | 'Deny';

export type ExternalRuntimeKind = 'claude_code' | 'codex' | 'other';

export type ExternalConnectionMode = 'Connected' | 'Managed';

export type ExternalHubTier = 'Off' | 'Build' | 'Admin';

export type AgentExecutionMode = 'Native' | 'Connected External' | 'Managed External';

export type ExternalSessionState =
  | 'Active'
  | 'Waiting for Input'
  | 'Waiting for Approval'
  | 'Runtime Offline'
  | 'Completed'
  | 'Failed'
  | 'Cancelled';

export interface ExternalConnection {
  name: string;
  user?: string;
  agent: string;
  runtime_kind: ExternalRuntimeKind;
  mode: ExternalConnectionMode;
  enabled: 0 | 1;
  read_policy: ExternalPolicy;
  write_policy: ExternalPolicy;
  communicate_policy: ExternalPolicy;
  hub_tier: ExternalHubTier;
  last_seen?: string | null;
}

export interface ConnectionTestResult {
  ok: boolean;
  agent: string | null;
  tools: number;
  enabled: boolean;
  policy: {
    read: ExternalPolicy;
    write: ExternalPolicy;
    communicate: ExternalPolicy;
  };
  hub_tier: ExternalHubTier;
  problems: string[];
}

export interface ConnectionSnippets {
  url: string;
  header_name: string;
  header_value_template: string;
  connection_header: string;
  connection: string;
}

export interface ExternalSession {
  name: string;
  connection: string;
  agent: string;
  state: ExternalSessionState;
  visibility_mode: 'Connected' | 'Huf-managed';
  conversation?: string | null;
  agent_run?: string | null;
  creation: string;
  ended_at?: string | null;
}

export interface ExternalEvent {
  seq: number;
  direction: 'to_agent' | 'from_agent';
  event_type: string;
  payload: Record<string, unknown>;
  status: string;
}

export interface ExternalApproval {
  name: string;
  session: string;
  tool_name: string;
  action_class: 'read' | 'write' | 'communicate';
  args: Record<string, unknown>;
  expires_on: string;
}

export interface ConnectableAgent {
  name: string;
  agent_name: string;
  execution_mode: AgentExecutionMode;
}

export interface CreateExternalConnectionInput {
  agent: string;
  runtime_kind?: ExternalRuntimeKind;
  mode?: ExternalConnectionMode;
  read_policy?: ExternalPolicy;
  write_policy?: ExternalPolicy;
  communicate_policy?: ExternalPolicy;
  hub_tier?: ExternalHubTier;
}

export interface AssignedTask {
  session: string;
  seq: number;
}
