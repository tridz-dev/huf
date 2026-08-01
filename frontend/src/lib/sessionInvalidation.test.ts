import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosError } from 'axios';

import { isSessionInvalidatedError } from './sessionInvalidation';

function makeError(status: number, exception?: string): AxiosError<{ exception?: string }> {
  return {
    isAxiosError: true,
    name: 'AxiosError',
    message: 'error',
    toJSON: () => ({}),
    config: {} as never,
    response: {
      status,
      data: { exception },
      statusText: '',
      headers: {},
      config: {} as never,
    },
  } as AxiosError<{ exception?: string }>;
}

describe('isSessionInvalidatedError', () => {
  it('matches the exact "is not whitelisted" 403 signature', () => {
    const error = makeError(403, 'frappe.exceptions.PermissionError: Function foo.bar is not whitelisted.');
    expect(isSessionInvalidatedError(error)).toBe(true);
  });

  it('does not match a real capability-denial 403 with a different message', () => {
    const error = makeError(403, 'frappe.exceptions.PermissionError: Insufficient Permission for Agent');
    expect(isSessionInvalidatedError(error)).toBe(false);
  });

  it('does not match a non-403 status', () => {
    const error = makeError(400, 'Function foo.bar is not whitelisted.');
    expect(isSessionInvalidatedError(error)).toBe(false);
  });

  it('does not match a 403 with no exception field', () => {
    const error = makeError(403, undefined);
    expect(isSessionInvalidatedError(error)).toBe(false);
  });
});

describe('notifySessionInvalidated', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('calls the registered handler', async () => {
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);
    mod.notifySessionInvalidated();
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('only calls the handler once even if notified multiple times (debounced per page life)', async () => {
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);
    mod.notifySessionInvalidated();
    mod.notifySessionInvalidated();
    mod.notifySessionInvalidated();
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
