import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

const API_MODULE = 'huf.ai.subscription_api';

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
