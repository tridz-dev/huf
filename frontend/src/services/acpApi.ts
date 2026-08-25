import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';
import { createToolFunction, getToolFunctions } from './toolApi';

/** ACP Command Registry document (admin-curated launch allow-list). */
export interface AcpRegistryEntry {
  name: string;
  registry_name: string;
  enabled: 0 | 1;
  binary_path: string;
  argv_shape: string | string[];
  working_directory: string;
  auth_required: 0 | 1;
  auth_env_key?: string;
  max_wall_time_seconds: number;
  notes?: string;
}

/** Remote Agent Connection document. */
export interface AcpConnection {
  name: string;
  connection_name: string;
  enabled: 0 | 1;
  protocol_type: string;
  acp_registry_entry?: string;
  auth_secret?: string;
  max_concurrent_sessions?: number;
  session_ttl_seconds?: number;
  base_url?: string;
  transport?: string;
  health_status?: 'unknown' | 'healthy' | 'degraded' | 'failed';
  last_health_check?: string;
  last_error?: string;
}

/** Remote Agent Policy document. */
export interface AcpPolicy {
  name: string;
  policy_name: string;
  enabled: 0 | 1;
  caller_type: 'api_key' | 'remote_connection' | 'user';
  caller_reference?: string;
  scope_type: 'single_agent' | 'agent_list';
  default_agent?: string;
  allowed_agents?: { agent: string }[];
  capability_scope?: string;
  max_run_duration_seconds: number;
  allow_file_tools: 0 | 1;
  allow_shell_tools: 0 | 1;
  notes?: string;
}

/** Result returned by a connection health probe. */
export interface AcpConnectionTestResult {
  ok: boolean;
  protocol_version?: number;
  agent_name?: string;
  error?: string;
}

const CONNECTION_LIST_FIELDS = [
  'name',
  'connection_name',
  'enabled',
  'protocol_type',
  'acp_registry_entry',
  'auth_secret',
  'max_concurrent_sessions',
  'session_ttl_seconds',
  'base_url',
  'transport',
  'health_status',
  'last_health_check',
  'last_error',
];

const POLICY_LIST_FIELDS = [
  'name',
  'policy_name',
  'enabled',
  'caller_type',
  'caller_reference',
  'scope_type',
  'default_agent',
  'capability_scope',
  'max_run_duration_seconds',
  'allow_file_tools',
  'allow_shell_tools',
  'notes',
];

/** Load all ACP stdio connections. */
export async function getAcpConnections(): Promise<AcpConnection[]> {
  try {
    const rows = await db.getDocList(doctype['Remote Agent Connection'], {
      fields: CONNECTION_LIST_FIELDS,
      filters: [['protocol_type', '=', 'acp_stdio']],
      orderBy: { field: 'modified', order: 'desc' },
      limit: 1000,
    });
    return rows as AcpConnection[];
  } catch (error) {
    handleFrappeError(error, 'Error loading ACP connections');
  }
}

/** Load all ACP command registry entries for the connection setup dropdown. */
export async function getAcpRegistryEntries(): Promise<AcpRegistryEntry[]> {
  try {
    const rows = await db.getDocList(doctype['ACP Command Registry'], {
      fields: [
        'name',
        'registry_name',
        'enabled',
        'binary_path',
        'argv_shape',
        'working_directory',
        'auth_required',
        'auth_env_key',
        'max_wall_time_seconds',
        'notes',
      ],
      filters: [['enabled', '=', 1]],
      orderBy: { field: 'registry_name', order: 'asc' },
      limit: 1000,
    });
    return rows as AcpRegistryEntry[];
  } catch (error) {
    handleFrappeError(error, 'Error loading ACP command registry');
  }
}

/** Create a new Remote Agent Connection. */
export async function createAcpConnection(
  data: Omit<AcpConnection, 'name'>
): Promise<AcpConnection> {
  try {
    const created = await db.createDoc(doctype['Remote Agent Connection'], {
      ...data,
      protocol_type: 'acp_stdio',
    });
    return created as AcpConnection;
  } catch (error) {
    handleFrappeError(error, 'Error creating ACP connection');
  }
}

/** Update an existing Remote Agent Connection. */
export async function updateAcpConnection(
  name: string,
  data: Partial<AcpConnection>
): Promise<AcpConnection> {
  try {
    const updated = await db.updateDoc(doctype['Remote Agent Connection'], name, data);
    return updated as AcpConnection;
  } catch (error) {
    handleFrappeError(error, 'Error updating ACP connection');
  }
}

/** Delete a Remote Agent Connection. */
export async function deleteAcpConnection(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Remote Agent Connection'], name);
  } catch (error) {
    handleFrappeError(error, 'Error deleting ACP connection');
  }
}

/**
 * Test an ACP connection by spawning the subprocess and running the initialize
 * handshake.
 *
 * TODO(PF.2-backend): This calls a whitelisted method that does not exist yet.
 * The backend needs `huf.ai.acp.tool_handler.test_acp_connection` (or similar)
 * that spawns the configured command, runs the ACP `initialize` handshake, and
 * returns `{ok, protocol_version, agent_name, error}`. Until then the UI will
 * surface a clear "not wired" message instead of failing silently.
 */
export async function testAcpConnection(
  connectionName: string
): Promise<AcpConnectionTestResult> {
  try {
    const response = (await call.post(
      'huf.ai.acp.tool_handler.test_acp_connection',
      { connection_name: connectionName }
    )) as { message?: AcpConnectionTestResult };
    return response?.message ?? { ok: false, error: 'No response from server' };
  } catch (error) {
    handleFrappeError(error, 'Error testing ACP connection');
  }
}

/** Load all Remote Agent Policies. */
export async function getAcpPolicies(): Promise<AcpPolicy[]> {
  try {
    const rows = await db.getDocList(doctype['Remote Agent Policy'], {
      fields: POLICY_LIST_FIELDS,
      orderBy: { field: 'modified', order: 'desc' },
      limit: 1000,
    });
    return (rows as AcpPolicy[]).map((p) => ({
      ...p,
      allowed_agents: p.allowed_agents || [],
    }));
  } catch (error) {
    handleFrappeError(error, 'Error loading remote agent policies');
  }
}

/** Create a new Remote Agent Policy. */
export async function createAcpPolicy(data: Omit<AcpPolicy, 'name'>): Promise<AcpPolicy> {
  try {
    const created = await db.createDoc(doctype['Remote Agent Policy'], data);
    return created as AcpPolicy;
  } catch (error) {
    handleFrappeError(error, 'Error creating remote agent policy');
  }
}

/** Update an existing Remote Agent Policy. */
export async function updateAcpPolicy(
  name: string,
  data: Partial<AcpPolicy>
): Promise<AcpPolicy> {
  try {
    const updated = await db.updateDoc(doctype['Remote Agent Policy'], name, data);
    return updated as AcpPolicy;
  } catch (error) {
    handleFrappeError(error, 'Error updating remote agent policy');
  }
}

/** Delete a Remote Agent Policy. */
export async function deleteAcpPolicy(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Remote Agent Policy'], name);
  } catch (error) {
    handleFrappeError(error, 'Error deleting remote agent policy');
  }
}

/** Convert a display name to a valid tool-name identifier. */
export function toAcpToolNameSlug(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/_{2,}/g, '_')
    .replace(/^[_-]+|[_-]+$/g, '')
    .slice(0, 128);
}

/** Find or create the Agent Tool Function that wraps a given ACP connection. */
export async function ensureRemoteAcpToolForConnection(
  connection: AcpConnection,
  toolTypes: AgentToolType[]
): Promise<AgentToolFunctionRef> {
  const slug = toAcpToolNameSlug(connection.connection_name);
  const toolName = slug ? `acp_${slug}` : `acp_${connection.name}`;

  const existing = await getToolFunctions();
  const match = existing.find(
    (t) =>
      t.types === 'Remote ACP Agent' &&
      t.function_path === 'huf.ai.acp.tool_handler.run_acp_agent_tool' &&
      t.tool_name === toolName
  );
  if (match) return match;

  const toolType =
    toolTypes.find((tt) => tt.name1 === 'Custom Function') ??
    toolTypes.find((tt) => tt.name1 === 'Platform Utility') ??
    toolTypes[0];

  return createToolFunction({
    tool_name: toolName,
    tool_type: toolType?.name || 'Custom Function',
    types: 'Remote ACP Agent',
    description: `Call the remote ACP agent "${connection.connection_name}"`,
    function_path: 'huf.ai.acp.tool_handler.run_acp_agent_tool',
    is_read_only: false,
    allowed_for_guest: false,
  });
}


// Temporary helper used only while the chat UI needs to identify ACP calls.
// Once the backend surfaces tool type/function_path on chat tool events, this
// can be removed in favour of a type check.
export function isRemoteAcpToolName(toolName?: string): boolean {
  return typeof toolName === 'string' && toolName.startsWith('acp_');
}
