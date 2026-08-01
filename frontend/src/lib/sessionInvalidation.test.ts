import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosError } from 'axios';

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
  beforeEach(() => {
    vi.resetModules();
  });

  it('matches the exact "is not whitelisted" 403 signature', async () => {
    const mod = await import('./sessionInvalidation');
    const error = makeError(403, 'frappe.exceptions.PermissionError: Function foo.bar is not whitelisted.');
    expect(mod.isSessionInvalidatedError(error)).toBe(true);
  });

  it('does not match a real capability-denial 403 with a different message', async () => {
    const mod = await import('./sessionInvalidation');
    const error = makeError(403, 'frappe.exceptions.PermissionError: Insufficient Permission for Agent');
    expect(mod.isSessionInvalidatedError(error)).toBe(false);
  });

  it('does not match a non-403 status', async () => {
    const mod = await import('./sessionInvalidation');
    const error = makeError(400, 'Function foo.bar is not whitelisted.');
    expect(mod.isSessionInvalidatedError(error)).toBe(false);
  });

  it('does not match a 403 with no exception field', async () => {
    const mod = await import('./sessionInvalidation');
    const error = makeError(403, undefined);
    expect(mod.isSessionInvalidatedError(error)).toBe(false);
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

describe('createSessionInvalidationHandler', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('does not notify logout when the confirmation call succeeds (transient 403)', async () => {
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);

    const axiosInstance = {
      get: vi.fn().mockResolvedValue({ data: { message: 'fresh-token' } }),
    } as unknown as Parameters<typeof mod.createSessionInvalidationHandler>[0];

    const interceptor = mod.createSessionInvalidationHandler(axiosInstance);
    const error = makeError(403, 'frappe.exceptions.PermissionError: Function foo.bar is not whitelisted.');
    await expect(interceptor(error)).rejects.toBe(error);

    expect(axiosInstance.get).toHaveBeenCalledWith(
      '/api/method/huf.ai.session_api.get_csrf_token',
      expect.objectContaining({ _sessionCheck: true }),
    );
    expect(handler).not.toHaveBeenCalled();
  });

  it('notifies logout when both the original and confirmation call fail', async () => {
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);

    const axiosInstance = {
      get: vi.fn().mockRejectedValue(new Error('session dead')),
    } as unknown as Parameters<typeof mod.createSessionInvalidationHandler>[0];

    const interceptor = mod.createSessionInvalidationHandler(axiosInstance);
    const error = makeError(403, 'frappe.exceptions.PermissionError: Function foo.bar is not whitelisted.');
    await expect(interceptor(error)).rejects.toBe(error);

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('ignores non-session 403 errors', async () => {
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);

    const axiosInstance = { get: vi.fn() } as unknown as Parameters<typeof mod.createSessionInvalidationHandler>[0];
    const interceptor = mod.createSessionInvalidationHandler(axiosInstance);

    const error = makeError(403, 'frappe.exceptions.PermissionError: Insufficient Permission for Agent');
    await expect(interceptor(error)).rejects.toBe(error);

    expect(axiosInstance.get).not.toHaveBeenCalled();
    expect(handler).not.toHaveBeenCalled();
  });

  it('does not run confirmation for the confirmation request itself', async () => {
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);

    const axiosInstance = { get: vi.fn() } as unknown as Parameters<typeof mod.createSessionInvalidationHandler>[0];
    const interceptor = mod.createSessionInvalidationHandler(axiosInstance);

    const error = makeError(403, 'frappe.exceptions.PermissionError: Function foo.bar is not whitelisted.');
    (error.config as { _sessionCheck?: boolean }) = { _sessionCheck: true };

    await expect(interceptor(error)).rejects.toBe(error);

    expect(axiosInstance.get).not.toHaveBeenCalled();
    expect(handler).not.toHaveBeenCalled();
  });
});
