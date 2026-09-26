import { call, db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';
import { fetchPaginatedCount } from './utilsApi';

const API_MODULE = 'huf.ai.subscription_api';

export interface SubscriptionRuntimeDoc {
  name: string;
  runtime_name: string;
  enabled?: 0 | 1;
  runtime_mode?: string;
  provider_family: 'Claude' | 'Codex' | 'Gemini';
  cli_type?: string;
  cli_path?: string;
  transport_type: 'Local' | 'Docker' | 'SSH';
  working_directory?: string;
  execution_user_hint?: string;
  ssh_connection?: string;
  docker_container?: string;
  docker_context?: string;
  docker_workdir?: string;
  timeout_seconds?: number;
  max_output_bytes?: number;
  owner_user?: string;
  tenancy_policy?: 'owner_only' | 'explicit_users' | 'explicit_roles' | 'system_managed_shared';
  allowed_users_json?: string;
  allowed_roles_json?: string;
  detected_version?: string;
  last_tested_on?: string;
  last_test_status?: string;
  last_error?: string;
  capabilities_snapshot?: string;
  auth_status?: 'unknown' | 'ready' | 'required' | 'waiting_user' | 'verifying' | 'failed';
  auth_method?: string;
  auth_account_hint?: string;
  last_auth_checked_at?: string;
  last_auth_success_at?: string;
  last_auth_failure_at?: string;
  auth_error_code?: string;
  auth_error_message?: string;
  modified?: string;
}

export interface GetSubscriptionRuntimesParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: 'enabled' | 'disabled' | 'all';
  [key: string]: unknown;
}

export interface PaginatedSubscriptionRuntimesResponse {
  items: SubscriptionRuntimeDoc[];
  hasMore: boolean;
  total?: number;
}

const SUBSCRIPTION_RUNTIME_LIST_FIELDS = [
  'name',
  'runtime_name',
  'enabled',
  'provider_family',
  'transport_type',
  'auth_status',
  'last_tested_on',
  'last_test_status',
  'modified',
];

/** Fetch a page of Subscription Runtime records for the list view. */
export async function getSubscriptionRuntimes(
  params: GetSubscriptionRuntimesParams = {}
): Promise<PaginatedSubscriptionRuntimesResponse> {
  try {
    const { page = 1, limit = 20, start = (page - 1) * limit, search, status = 'all' } = params;
    const filters: Array<[string, string, string | number | boolean]> = [];

    if (status === 'enabled') {
      filters.push(['enabled', '=', 1]);
    } else if (status === 'disabled') {
      filters.push(['enabled', '=', 0]);
    }

    if (search && search.trim()) {
      filters.push(['runtime_name', 'like', `%${search.trim()}%`]);
    }

    const runtimes = await db.getDocList(doctype['Subscription Runtime'], {
      fields: SUBSCRIPTION_RUNTIME_LIST_FIELDS,
      filters: filters.length > 0 ? (filters as never) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mapped = runtimes as SubscriptionRuntimeDoc[];
    const hasMore = mapped.length > limit;
    const items = hasMore ? mapped.slice(0, limit) : mapped;
    const total = await fetchPaginatedCount(page, items.length, doctype['Subscription Runtime'], filters);

    return { items, hasMore, total };
  } catch (error) {
    handleFrappeError(error, 'Error fetching subscription runtimes');
    throw error;
  }
}

/** Fetch a single Subscription Runtime by name (has no secret fields to leak). */
export async function getSubscriptionRuntime(name: string): Promise<SubscriptionRuntimeDoc> {
  try {
    const response = await db.getDoc(doctype['Subscription Runtime'], name);
    return response as SubscriptionRuntimeDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function createSubscriptionRuntime(
  data: Partial<SubscriptionRuntimeDoc>
): Promise<SubscriptionRuntimeDoc> {
  try {
    const response = await db.createDoc(doctype['Subscription Runtime'], data);
    return response as SubscriptionRuntimeDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateSubscriptionRuntime(
  name: string,
  data: Partial<SubscriptionRuntimeDoc>
): Promise<SubscriptionRuntimeDoc> {
  try {
    const response = await db.updateDoc(doctype['Subscription Runtime'], name, data);
    return response as SubscriptionRuntimeDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteSubscriptionRuntime(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Subscription Runtime'], name);
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export interface SubscriptionRuntimeProbeResult {
  success: boolean;
  runtime: string;
  cli: string;
  version: string | null;
  authenticated: boolean;
  session_resume: boolean;
  structured_output: boolean;
  streaming: boolean;
  vision: boolean;
  usage: boolean;
  mcp: boolean;
  error?: string;
}

export interface SubscriptionAuthChallenge {
  name: string;
  runtime: string;
  provider: string;
  status: 'Pending' | 'Waiting User' | 'Verifying' | 'Success' | 'Failed' | 'Expired' | 'Cancelled';
  mode: 'browser' | 'device_code' | 'terminal_code' | 'manual_command' | 'unsupported' | null;
  verification_url: string | null;
  user_code: string | null;
  safe_instructions: string | null;
  expires_at: string | null;
}

export interface SubscriptionAuthStatus {
  state: string;
  account_hint: string | null;
  method: string | null;
  message: string | null;
  checked_at: string;
}

export interface SubscriptionAuthCancelResult {
  success: boolean;
  challenge: string;
  status: string;
}

export interface SubscriptionRuntimeLogoutResult {
  success: boolean;
  runtime: string;
  auth_status: string;
}

/** Probe a Subscription CLI runtime: version, capabilities, auth state. */
export async function testSubscriptionRuntimeConnection(
  runtimeName: string
): Promise<SubscriptionRuntimeProbeResult> {
  try {
    const response = await call.post(`${API_MODULE}.test_subscription_runtime_connection`, {
      runtime_name: runtimeName,
    });
    return response.message as SubscriptionRuntimeProbeResult;
  } catch (error) {
    handleFrappeError(error, 'Error testing subscription runtime connection');
    throw error;
  }
}

/** Re-run the probe for a runtime and persist the refreshed capability snapshot. */
export async function refreshSubscriptionRuntimeProbe(
  runtimeName: string
): Promise<SubscriptionRuntimeProbeResult> {
  try {
    const response = await call.post(`${API_MODULE}.refresh_subscription_runtime_probe`, {
      runtime_name: runtimeName,
    });
    return response.message as SubscriptionRuntimeProbeResult;
  } catch (error) {
    handleFrappeError(error, 'Error refreshing subscription runtime probe');
    throw error;
  }
}

/** Start (or resume) a login challenge for a subscription runtime. */
export async function beginSubscriptionAuth(runtimeName: string): Promise<SubscriptionAuthChallenge> {
  try {
    const response = await call.post(`${API_MODULE}.begin_subscription_auth`, {
      runtime_name: runtimeName,
    });
    return response.message as SubscriptionAuthChallenge;
  } catch (error) {
    handleFrappeError(error, 'Error starting subscription authentication');
    throw error;
  }
}

/** Poll an in-flight login challenge for completion. */
export async function pollSubscriptionAuth(challengeName: string): Promise<SubscriptionAuthStatus> {
  try {
    const response = await call.post(`${API_MODULE}.poll_subscription_auth`, {
      challenge_name: challengeName,
    });
    return response.message as SubscriptionAuthStatus;
  } catch (error) {
    handleFrappeError(error, 'Error polling subscription authentication');
    throw error;
  }
}

/**
 * Submit a user-provided value to an in-flight login challenge (e.g. a
 * device-code confirmation or one-time paste-back token). Never a password.
 */
export async function submitSubscriptionAuthInput(
  challengeName: string,
  value: string
): Promise<SubscriptionAuthStatus> {
  try {
    const response = await call.post(`${API_MODULE}.submit_subscription_auth_input`, {
      challenge_name: challengeName,
      value,
    });
    return response.message as SubscriptionAuthStatus;
  } catch (error) {
    handleFrappeError(error, 'Error submitting subscription authentication input');
    throw error;
  }
}

/** Cancel an in-flight login challenge. */
export async function cancelSubscriptionAuth(
  challengeName: string
): Promise<SubscriptionAuthCancelResult> {
  try {
    const response = await call.post(`${API_MODULE}.cancel_subscription_auth`, {
      challenge_name: challengeName,
    });
    return response.message as SubscriptionAuthCancelResult;
  } catch (error) {
    handleFrappeError(error, 'Error cancelling subscription authentication');
    throw error;
  }
}

/** Convenience wrapper: starts a fresh login challenge for an already-configured runtime. */
export async function reauthenticateSubscriptionRuntime(
  runtimeName: string
): Promise<SubscriptionAuthChallenge> {
  try {
    const response = await call.post(`${API_MODULE}.reauthenticate_subscription_runtime`, {
      runtime_name: runtimeName,
    });
    return response.message as SubscriptionAuthChallenge;
  } catch (error) {
    handleFrappeError(error, 'Error re-authenticating subscription runtime');
    throw error;
  }
}

/** Log out a Subscription Runtime. Requires manage permission — affects every tenant. */
export async function logoutSubscriptionRuntime(
  runtimeName: string
): Promise<SubscriptionRuntimeLogoutResult> {
  try {
    const response = await call.post(`${API_MODULE}.logout_subscription_runtime`, {
      runtime_name: runtimeName,
    });
    return response.message as SubscriptionRuntimeLogoutResult;
  } catch (error) {
    handleFrappeError(error, 'Error logging out subscription runtime');
    throw error;
  }
}
