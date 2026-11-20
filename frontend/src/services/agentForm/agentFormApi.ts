import { call } from '@/lib/frappe-sdk';

const BASE = 'huf.ai.agent.agent_form_api';

/** Thrown when an endpoint is not deployed yet, so the UI can say "needs backend update" or fall back. */
export class EndpointUnavailableError extends Error {
  readonly endpoint: string;
  constructor(endpoint: string, cause?: unknown) {
    super(`Backend endpoint ${endpoint} is not available. This needs a backend update.`);
    this.name = 'EndpointUnavailableError';
    this.endpoint = endpoint;
    (this as { cause?: unknown }).cause = cause;
  }
}

export const isEndpointUnavailable = (e: unknown): e is EndpointUnavailableError =>
  e instanceof EndpointUnavailableError;

function looksMissing(e: unknown): boolean {
  const x = e as { httpStatus?: number; status?: number; exc_type?: string; message?: string; exception?: string; response?: { status?: number } } | null;
  const status = x?.httpStatus ?? x?.status ?? x?.response?.status;
  const text = `${x?.exc_type ?? ''} ${x?.exception ?? ''} ${x?.message ?? ''}`;
  return status === 404 || /AttributeError|ImportError|ModuleNotFound|not whitelisted|has no attribute|No module named/i.test(text);
}

async function request<T>(method: 'get' | 'post', fn: string, params?: Record<string, unknown>): Promise<T> {
  const path = `${BASE}.${fn}`;
  try {
    const res = method === 'get' ? await call.get(path, params) : await call.post(path, params);
    return res.message as T;
  } catch (e) {
    if (looksMissing(e)) throw new EndpointUnavailableError(fn, e);
    throw e;
  }
}

export interface WorkspaceDefaultModel { provider: string | null; model: string | null }

export interface DraftOverrides {
  instructions?: string;
  provider?: string;
  model?: string;
  temperature?: number;
  top_p?: number;
  /** Tool function names. */
  agent_tool?: string[];
}

export interface DraftToolCall {
  tool: string;
  tool_args?: string | null;
  tool_result?: string | null;
  status?: string | null;
  error_message?: string | null;
}

export interface DraftTestResult {
  success: boolean;
  response: string | null;
  error?: string | null;
  error_code?: string | null;
  agent_run_id: string;
  conversation_id?: string;
  tool_calls: DraftToolCall[];
  latency_ms: number;
  tokens: { input?: number | null; output?: number | null; total?: number | null };
}

export interface DeletePrecheck {
  agent: string;
  counts: { conversations: number; runs: number; automations: number; triggers: number };
  has_linked: boolean;
  disabled: boolean;
  can_delete: boolean;
  can_archive: boolean;
  suggest_archive: boolean;
  archive_method: string;
  delete_method: string;
}

export const getWorkspaceDefaultModel = () =>
  request<WorkspaceDefaultModel>('get', 'get_workspace_default_model');

export const setWorkspaceDefaultModel = (provider: string | null, model: string) =>
  request<WorkspaceDefaultModel>('post', 'set_workspace_default_model', { provider, model });

export const runAgentDraftTest = (agentName: string, prompt: string, draftOverrides: DraftOverrides = {}) =>
  request<DraftTestResult>('post', 'run_agent_draft_test', {
    agent_name: agentName,
    prompt,
    draft_overrides: JSON.stringify(draftOverrides),
  });

export const getAgentDeletePrecheck = (agentName: string) =>
  request<DeletePrecheck>('get', 'get_agent_delete_precheck', { agent_name: agentName });

export async function archiveAgent(agentName: string): Promise<void> {
  await call.post('huf.huf.doctype.agent.agent.archive_agent', { agent_name: agentName });
}

export async function deleteAgentCascade(agentName: string): Promise<void> {
  await call.post('huf.huf.doctype.agent.agent.delete_agent_cascade', { agent_name: agentName });
}
