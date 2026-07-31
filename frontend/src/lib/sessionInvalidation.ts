import type { AxiosError } from 'axios';

/**
 * Frappe's is_whitelisted() throws this exact text whenever
 * `method not in whitelisted OR (is_guest AND method not in guest_methods)` -
 * both branches produce the identical "Function X is not whitelisted"
 * message. For any endpoint this build actually calls, "not registered" is
 * not a real possibility (it would fail on every request, not
 * intermittently) - so in practice this signature means the session
 * resolved to Guest for this specific request. Unlike a normal capability
 * denial (a different message, e.g. "Insufficient Permission for X" or a
 * huf.permissions "not permitted" string), this means the session itself is
 * gone, not that one feature is unavailable - see
 * Tracks/safwan-erooth.AuthDebug/FINDINGS.md ("Bug C") in the workspace repo.
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
