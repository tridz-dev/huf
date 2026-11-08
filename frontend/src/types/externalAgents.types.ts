/**
 * Types for external agent connections (Claude Code, Codex, other runtimes)
 * and their sessions, events and approvals.
 */

export type ExternalPolicy = 'Allow' | 'Requires Approval' | 'Deny';

export type ExternalRuntimeKind = 'claude_code' | 'codex' | 'other';

export type ExternalConnectionMode = 'Connected' | 'Managed';

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
  last_seen?: string | null;
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
}
