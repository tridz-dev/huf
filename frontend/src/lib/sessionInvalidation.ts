import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

/**
 * Frappe's is_whitelisted() throws this exact text whenever
 * `method not in whitelisted OR (is_guest AND method not in guest_methods)` -
 * both branches produce the identical "Function X is not whitelisted"
 * message. For any endpoint this build actually calls, "not registered" is
 * not a real possibility (it would fail on every request, not
 * intermittently) - so in practice this signature means the session resolved
 * to Guest for this specific request. Unlike a normal capability denial (a
 * different message, e.g. "Insufficient Permission for X" or a
 * huf.permissions "not permitted" string), this means the session itself is
 * gone, not that one feature is unavailable.
 */
const NOT_WHITELISTED_PATTERN = /is not whitelisted/i;

export function isSessionInvalidatedError(error: AxiosError<{ exception?: string }>): boolean {
  if (error.response?.status !== 403) return false;
  const exception = error.response?.data?.exception;
  return typeof exception === 'string' && NOT_WHITELISTED_PATTERN.test(exception);
}

let handler: (() => void) | null = null;
let notified = false;

/** Called once by UserContext on mount to receive session-death notifications. */
export function onSessionInvalidated(fn: () => void): void {
  handler = fn;
}

/**
 * Notify the registered handler at most once per page life - a burst of
 * concurrent requests can all hit this signature together, and we only want
 * one clean redirect, not N of them racing.
 */
export function notifySessionInvalidated(): void {
  if (notified) return;
  notified = true;
  handler?.();
}

interface SessionCheckRequestConfig extends InternalAxiosRequestConfig {
  _sessionCheck?: boolean;
}

/**
 * Create an axios response interceptor that detects the dead-session
 * signature (403 + "is not whitelisted") and confirms it before logging the
 * user out.
 *
 * A single request can hit this signature transiently: cold worker, cache
 * clear, or a brief race where one request is processed before the session
 * cookie is fully established. In those cases the session cookie is still
 * valid, so forcing a logout is destructive. We make one lightweight
 * confirmation call (bypassing this interceptor via `_sessionCheck`) and only
 * trigger the global logout if that call also fails.
 */
export function createSessionInvalidationHandler(axiosInstance: AxiosInstance) {
  let checking = false;

  const confirmSessionInvalidated = async (): Promise<boolean> => {
    if (checking) return true; // another request is already confirming; treat as dead for now
    checking = true;
    try {
      await axiosInstance.get('/api/method/huf.ai.session_api.get_csrf_token', {
        _sessionCheck: true,
      } as SessionCheckRequestConfig);
      // Token endpoint succeeded -> session is alive; the 403 was transient.
      return false;
    } catch {
      // Confirmation also failed -> session is genuinely gone.
      return true;
    } finally {
      checking = false;
    }
  };

  return async (error: AxiosError<{ exception?: string }>) => {
    const config = error.config as SessionCheckRequestConfig | undefined;

    if (isSessionInvalidatedError(error) && !config?._sessionCheck) {
      const isReallyDead = await confirmSessionInvalidated();
      if (isReallyDead) {
        notifySessionInvalidated();
      }
    }

    return Promise.reject(error);
  };
}
