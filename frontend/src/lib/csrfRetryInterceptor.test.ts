import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosError, AxiosInstance } from 'axios';

import { createCsrfRetryHandler } from './csrfRetryInterceptor';

// This test suite runs under vitest's default 'node' environment (no jsdom),
// so stub the minimal `window` surface the interceptor touches.
beforeEach(() => {
  (globalThis as unknown as { window: { csrf_token?: string } }).window = {};
});

function makeCsrfError(overrides: Partial<AxiosError> = {}): AxiosError<{ exc_type?: string }> {
  return {
    isAxiosError: true,
    name: 'AxiosError',
    message: 'Invalid Request',
    toJSON: () => ({}),
    config: { headers: { set: vi.fn() } } as never,
    response: {
      status: 400,
      data: { exc_type: 'CSRFTokenError' },
      statusText: 'Bad Request',
      headers: {},
      config: {} as never,
    },
    ...overrides,
  } as AxiosError<{ exc_type?: string }>;
}

describe('createCsrfRetryHandler', () => {
  afterEach(() => {
    delete (globalThis as unknown as { window?: { csrf_token?: string } }).window;
  });

  it('fetches a fresh token and retries the original request once on a CSRFTokenError', async () => {
    const retriedResponse = { data: { message: 'saved' } };
    const axiosInstance = {
      get: vi.fn().mockResolvedValue({ data: { message: 'fresh-token' } }),
      request: vi.fn().mockResolvedValue(retriedResponse),
    } as unknown as AxiosInstance;

    const handler = createCsrfRetryHandler(axiosInstance);
    const error = makeCsrfError();

    const result = await handler(error);

    expect(axiosInstance.get).toHaveBeenCalledWith('/api/method/huf.ai.session_api.get_csrf_token');
    expect(error.config!.headers.set).toHaveBeenCalledWith('X-Frappe-CSRF-Token', 'fresh-token');
    expect(
      (globalThis as unknown as { window: { csrf_token?: string } }).window.csrf_token,
    ).toBe('fresh-token');
    expect(axiosInstance.request).toHaveBeenCalledWith(error.config);
    expect(result).toBe(retriedResponse);
  });

  it('does not retry a second time for the same request (prevents infinite loops)', async () => {
    const axiosInstance = {
      get: vi.fn().mockResolvedValue({ data: { message: 'fresh-token' } }),
      request: vi.fn().mockResolvedValue({}),
    } as unknown as AxiosInstance;

    const handler = createCsrfRetryHandler(axiosInstance);
    const error = makeCsrfError();
    (error.config as { _csrfRetried?: boolean })._csrfRetried = true;

    await expect(handler(error)).rejects.toBe(error);
    expect(axiosInstance.get).not.toHaveBeenCalled();
    expect(axiosInstance.request).not.toHaveBeenCalled();
  });

  it('rejects with the original error when the token refresh itself fails (real logout case)', async () => {
    const axiosInstance = {
      get: vi.fn().mockRejectedValue(new Error('not authenticated')),
      request: vi.fn(),
    } as unknown as AxiosInstance;

    const handler = createCsrfRetryHandler(axiosInstance);
    const error = makeCsrfError();

    await expect(handler(error)).rejects.toBe(error);
    expect(axiosInstance.request).not.toHaveBeenCalled();
  });

  it('passes through non-CSRF errors unchanged', async () => {
    const axiosInstance = {
      get: vi.fn(),
      request: vi.fn(),
    } as unknown as AxiosInstance;

    const handler = createCsrfRetryHandler(axiosInstance);
    const error = makeCsrfError({
      response: {
        status: 403,
        data: { exc_type: 'PermissionError' },
        statusText: 'Forbidden',
        headers: {},
        config: {} as never,
      },
    });

    await expect(handler(error)).rejects.toBe(error);
    expect(axiosInstance.get).not.toHaveBeenCalled();
  });
});
