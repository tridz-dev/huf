import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

/**
 * Frappe's is_whitelisted() throws this exact text whenever
 * `method not in whitelisted OR (is_guest AND method not in guest_methods)` -
 * both branches produce the identical "Function X is not whitelisted"
 * message. For any endpoint this build actually calls, "not registered" is
 * not a real possibility (it would fail on every request, not
 * intermittently) - so in practice this signature means the session resolved
 * to Guest for this specific request (RPC-style /api/method/* calls).
 */
const NOT_WHITELISTED_PATTERN = /is not whitelisted/i;

/**
 * A definite signature: this text can only come from is_whitelisted(), so a
 * match means the session is confirmed dead without needing to check further.
 */
export function isSessionInvalidatedError(error: AxiosError<{ exception?: string }>): boolean {
  if (error.response?.status !== 403) return false;
  const exception = error.response?.data?.exception;
  return typeof exception === 'string' && NOT_WHITELISTED_PATTERN.test(exception);
}

/**
 * A Guest session hitting Frappe's REST API (/api/resource/*, used by
 * `db.getDocList` and most list/read calls) fails through a completely
 * different path - frappe/database/query.py's check_select_permission -
 * with the message "Insufficient Permission for X". That text is
 * indistinguishable from a genuine capability denial by content alone (both
 * are exc_type PermissionError), so this only flags it as *worth
 * confirming*, not as definite - unlike isSessionInvalidatedError, this can
 * false-positive on real denials, which is fine because the caller always
 * confirms before acting on it.
 */
function isPossibleSessionInvalidation(error: AxiosError<{ exc_type?: string }>): boolean {
  return error.response?.status === 403 && error.response?.data?.exc_type === 'PermissionError';
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
 * Create an axios response interceptor that detects a dead session - either
 * the definite RPC-style signature (403 + "is not whitelisted") or a
 * possible REST-style one (any 403 PermissionError, e.g. "Insufficient
 * Permission for X" from `db.getDocList`/`/api/resource/*` calls) - and
 * confirms it before logging the user out.
 *
 * A single request can hit either signature transiently: cold worker, cache
 * clear, or a brief race where one request is processed before the session
 * cookie is fully established. In those cases the session cookie is still
 * valid, so forcing a logout is destructive. We make one lightweight
 * confirmation call (bypassing this interceptor via `_sessionCheck`) and only
 * trigger the global logout if that call also fails. The REST-style
 * signature is indistinguishable from a genuine capability denial by message
 * text alone, so it's only ever treated as "worth confirming" - the
 * confirmation is what actually decides, and it's a safe no-op for real
 * denials (their own error still surfaces to the caller either way).
 *
 * Concurrent 403s share the same in-flight confirmation instead of each
 * assuming the worst - otherwise a burst of legitimate, unrelated denials
 * arriving together could trigger a false logout for every one after the
 * first, before any of them actually know the real answer.
 */
export function createSessionInvalidationHandler(axiosInstance: AxiosInstance) {
  let inFlight: Promise<boolean> | null = null;

  const confirmSessionInvalidated = (): Promise<boolean> => {
    if (inFlight) return inFlight;
    inFlight = (async () => {
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
        inFlight = null;
      }
    })();
    return inFlight;
  };

  return async (error: AxiosError<{ exception?: string; exc_type?: string }>) => {
    const config = error.config as SessionCheckRequestConfig | undefined;
    const worthConfirming =
      !config?._sessionCheck && (isSessionInvalidatedError(error) || isPossibleSessionInvalidation(error));

    if (worthConfirming) {
      const isReallyDead = await confirmSessionInvalidated();
      if (isReallyDead) {
        notifySessionInvalidated();
      }
    }

    return Promise.reject(error);
  };
}
