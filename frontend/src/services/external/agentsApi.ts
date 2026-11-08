/**
 * External Agents API functions
 *
 * Provides frontend API for external agent connections (Claude Code, Codex, other runtimes),
 * their sessions, events and approvals.
 */

import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type {
  AgentExecutionMode,
  ConnectableAgent,
  ConnectionSnippets,
  ConnectionTestResult,
  CreateExternalConnectionInput,
  ExternalApproval,
  ExternalConnection,
  ExternalEvent,
  ExternalSession,
} from '@/types/external/agents.types';

const BASE = 'huf.ai.external.api.';

/**
 * List external connections visible to the current user
 */
export async function listExternalConnections(): Promise<ExternalConnection[]> {
  try {
    const response = await call.get(`${BASE}list_connections`);
    return (response.message || []) as ExternalConnection[];
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Create an external connection for an agent. Returns the connection name.
 */
export async function createExternalConnection(input: CreateExternalConnectionInput): Promise<string> {
  try {
    const response = await call.post(`${BASE}create_connection`, input);
    return response.message as string;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Update the enabled flag or policies of an external connection
 */
export async function updateExternalConnection(
  name: string,
  patch: Partial<
    Pick<ExternalConnection, 'enabled' | 'read_policy' | 'write_policy' | 'communicate_policy' | 'hub_tier'>
  >,
): Promise<ExternalConnection> {
  try {
    const response = await call.post(`${BASE}update_connection`, { name, ...patch });
    return response.message as ExternalConnection;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Check whether a connection is ready to use. Returns plain-language problems when it is not.
 */
export async function testExternalConnection(connection: string): Promise<ConnectionTestResult> {
  try {
    const response = await call.post(`${BASE}test_connection`, { connection });
    return response.message as ConnectionTestResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Get the setup details (address and header format) for copying into a connected app
 */
export async function getConnectionSnippets(connection: string): Promise<ConnectionSnippets> {
  try {
    const response = await call.get(`${BASE}get_connection_snippets`, { connection });
    return response.message as ConnectionSnippets;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * List recent external sessions
 */
export async function listExternalSessions(limit = 20): Promise<ExternalSession[]> {
  try {
    const response = await call.get(`${BASE}list_sessions`, { limit });
    return (response.message || []) as ExternalSession[];
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Get the event log for an external session
 */
export async function getExternalSessionEvents(session: string, limit = 50): Promise<ExternalEvent[]> {
  try {
    const response = await call.get(`${BASE}get_session_events`, { session, limit });
    return (response.message || []) as ExternalEvent[];
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Send a user message into an external session
 */
export async function postExternalUserMessage(session: string, text: string): Promise<void> {
  try {
    await call.post(`${BASE}post_user_message`, { session, text });
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * List approvals waiting for a decision
 */
export async function listPendingExternalApprovals(): Promise<ExternalApproval[]> {
  try {
    const response = await call.get(`${BASE}list_pending_approvals`);
    return (response.message || []) as ExternalApproval[];
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Approve or deny a pending external approval
 */
export async function decideExternalApproval(
  approval: string,
  approve: boolean,
  comment?: string,
): Promise<void> {
  try {
    await call.post(`${BASE}decide`, {
      approval,
      approve: approve ? 1 : 0,
      ...(comment !== undefined && { comment }),
    });
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Cancel an external session
 */
export async function cancelExternalSession(session: string): Promise<void> {
  try {
    await call.post(`${BASE}cancel`, { session });
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * List agents that can be connected to an external runtime
 */
export async function listConnectableAgents(): Promise<ConnectableAgent[]> {
  try {
    const response = await call.get(`${BASE}list_connectable_agents`);
    return (response.message || []) as ConnectableAgent[];
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

/**
 * Set the execution mode of an agent
 */
export async function setAgentExecutionMode(agent: string, executionMode: AgentExecutionMode): Promise<void> {
  try {
    await call.post(`${BASE}set_agent_execution_mode`, { agent, execution_mode: executionMode });
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}
