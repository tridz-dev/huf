import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosError } from 'axios';

function makeError(
  status: number,
  exception?: string,
  excType?: string,
): AxiosError<{ exception?: string; exc_type?: string }> {
  return {
    isAxiosError: true,
    name: 'AxiosError',
    message: 'error',
    toJSON: () => ({}),
    config: {} as never,
    response: {
      status,
      data: { exception, exc_type: excType },
      statusText: '',
      headers: {},
      config: {} as never,
    },
  } as AxiosError<{ exception?: string; exc_type?: string }>;
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

  it('ignores 403s that are not shaped like a PermissionError at all', async () => {
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);

    const axiosInstance = { get: vi.fn() } as unknown as Parameters<typeof mod.createSessionInvalidationHandler>[0];
    const interceptor = mod.createSessionInvalidationHandler(axiosInstance);

    const error = makeError(403, 'Some other 403 entirely', 'ValidationError');
    await expect(interceptor(error)).rejects.toBe(error);

    expect(axiosInstance.get).not.toHaveBeenCalled();
    expect(handler).not.toHaveBeenCalled();
  });

  it('confirms (but does not log out) a REST-style "Insufficient Permission" 403 when the session is actually fine', async () => {
    // db.getDocList / /api/resource/* calls fail through a different Frappe
    // code path than is_whitelisted() and produce a differently-worded but
    // equally exc_type:PermissionError response when the session has become
    // Guest - this is the gap that let real session-death events through
    // undetected via list/read calls while the RPC-only check caught only
    // /api/method/* calls.
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);

    const axiosInstance = {
      get: vi.fn().mockResolvedValue({ data: { message: 'fresh-token' } }),
    } as unknown as Parameters<typeof mod.createSessionInvalidationHandler>[0];
    const interceptor = mod.createSessionInvalidationHandler(axiosInstance);

    const error = makeError(403, 'Insufficient Permission for Flow Definition', 'PermissionError');
    await expect(interceptor(error)).rejects.toBe(error);

    expect(axiosInstance.get).toHaveBeenCalledWith(
      '/api/method/huf.ai.session_api.get_csrf_token',
      expect.objectContaining({ _sessionCheck: true }),
    );
    // Confirmation succeeded -> this was a real, transient-or-genuine
    // permission response, not a dead session - the caller still sees their
    // own "Insufficient Permission" error (rejects.toBe(error) above), but
    // the app must not be logged out over it.
    expect(handler).not.toHaveBeenCalled();
  });

  it('logs out on a REST-style "Insufficient Permission" 403 when confirmation also fails', async () => {
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);

    const axiosInstance = {
      get: vi.fn().mockRejectedValue(new Error('session dead')),
    } as unknown as Parameters<typeof mod.createSessionInvalidationHandler>[0];
    const interceptor = mod.createSessionInvalidationHandler(axiosInstance);

    const error = makeError(403, 'Insufficient Permission for Flow Definition', 'PermissionError');
    await expect(interceptor(error)).rejects.toBe(error);

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight confirmation across concurrent 403s instead of assuming each is dead', async () => {
    // A burst of legitimate, unrelated denials arriving together must not
    // cause every request after the first to short-circuit to "dead" before
    // the real confirmation result is known.
    const mod = await import('./sessionInvalidation');
    const handler = vi.fn();
    mod.onSessionInvalidated(handler);

    let resolveGet!: (value: unknown) => void;
    const pendingGet = new Promise((resolve) => {
      resolveGet = resolve;
    });
    const axiosInstance = {
      get: vi.fn().mockReturnValue(pendingGet),
    } as unknown as Parameters<typeof mod.createSessionInvalidationHandler>[0];
    const interceptor = mod.createSessionInvalidationHandler(axiosInstance);

    const errorA = makeError(403, 'Insufficient Permission for Flow Definition', 'PermissionError');
    const errorB = makeError(403, 'Insufficient Permission for Integration Settings', 'PermissionError');

    const resultA = interceptor(errorA).catch((e) => e);
    const resultB = interceptor(errorB).catch((e) => e);

    // Only one confirmation call should be in flight for both concurrent 403s.
    expect(axiosInstance.get).toHaveBeenCalledTimes(1);

    resolveGet({ data: { message: 'fresh-token' } });
    await Promise.all([resultA, resultB]);

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
