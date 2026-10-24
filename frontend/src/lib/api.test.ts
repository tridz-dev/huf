// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const request = vi.fn();
vi.mock('@/lib/frappe-sdk', () => ({ frappe: { axios: { request: (c: unknown) => request(c) } } }));

import { ApiError, apiCall, methodUrl, normalizeError, toQueryParams, unwrapEnvelope } from './api';

const axiosErr = (status: number | undefined, data?: unknown, extra: Record<string, unknown> = {}) => ({
  isAxiosError: true,
  message: 'axios',
  ...(status !== undefined ? { response: { status, data } } : { request: {} }),
  ...extra,
});

describe('normalizeError', () => {
  const cases: Array<[string, unknown, Partial<ApiError>]> = [
    ['plain string', 'boom', { code: 'error', message: 'boom' }],
    ['Error instance', new Error('bad'), { code: 'error', message: 'bad' }],
    ['frappe exc_type + server messages', axiosErr(417, { exc_type: 'ValidationError', _server_messages: JSON.stringify([JSON.stringify({ message: '<b>Nope</b>' })]) }), { code: 'ValidationError', message: 'Nope', httpStatus: 417 }],
    ['frappe exception only', axiosErr(500, { exception: 'frappe.exceptions.PermissionError: denied' }), { code: 'PermissionError', httpStatus: 500 }],
    ['management envelope', axiosErr(200, { success: false, error: 'no_account', message: 'No account' }), { code: 'no_account', message: 'No account' }],
    ['management envelope w/o message', { success: false, error: 'bridge_unavailable' }, { code: 'bridge_unavailable', message: 'bridge_unavailable' }],
    ['v1 contract', axiosErr(404, { error: { code: 'not_found', message: 'Missing', status: 404 } }), { code: 'not_found', message: 'Missing', status: 404, httpStatus: 404 }],
    ['network failure (axios)', axiosErr(undefined), { code: 'network_error' }],
    ['network failure (fetch)', new TypeError('Failed to fetch'), { code: 'network_error' }],
    ['timeout code', { code: 'ECONNABORTED', message: 'timeout of 1ms' }, { code: 'timeout' }],
    ['abort (DOMException)', { name: 'AbortError', message: 'x' }, { code: 'aborted' }],
    ['abort (axios)', { code: 'ERR_CANCELED', message: 'canceled' }, { code: 'aborted' }],
    ['http error without body', axiosErr(502, '<html>'), { code: 'http_502', httpStatus: 502 }],
    ['unknown value', 42, { code: 'error' }],
  ];
  it.each(cases)('%s', (_n, input, expected) => {
    const e = normalizeError(input);
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject(expected);
    expect(e.raw).toBe(input);
  });
  it('is idempotent', () => {
    const e = normalizeError('x');
    expect(normalizeError(e)).toBe(e);
  });
});

describe('unwrapEnvelope', () => {
  it.each([
    ['frappe message envelope', { message: { a: 1 } }, { a: 1 }],
    ['frappe message scalar', { message: 'ok' }, 'ok'],
    ['bare success payload', { success: true, data: [1] }, { success: true, data: [1] }],
    ['null error field', { message: { error: null, v: 1 } }, { error: null, v: 1 }],
    ['non-object', 7, 7],
  ])('returns value: %s', (_n, input, out) => {
    expect(unwrapEnvelope(input)).toEqual(out);
  });
  it.each([
    ['top-level management', { success: false, error: 'x_err', message: 'm' }, 'x_err'],
    ['wrapped management', { message: { success: false, error: 'y_err' } }, 'y_err'],
    ['top-level v1', { error: { code: 'bad', message: 'm' } }, 'bad'],
    ['wrapped v1', { message: { error: { code: 'bad2', message: 'm' } } }, 'bad2'],
  ])('throws: %s', (_n, input, code) => {
    expect(() => unwrapEnvelope(input)).toThrowError(expect.objectContaining({ code }));
  });
});

describe('helpers', () => {
  it('methodUrl has one prefix', () => {
    expect(methodUrl('huf.a.b')).toBe('/api/method/huf.a.b');
    expect(methodUrl('/api/method/huf.a.b')).toBe('/api/method/huf.a.b');
  });
  it('toQueryParams stringifies objects and drops nullish', () => {
    const p = toQueryParams({ a: 1, b: { x: [1] }, c: null, d: undefined, e: 'z', f: false });
    expect(p.toString()).toBe('a=1&b=%7B%22x%22%3A%5B1%5D%7D&e=z&f=false');
  });
});

describe('apiCall', () => {
  beforeEach(() => { request.mockReset(); vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('GET sends query params and unwraps message', async () => {
    request.mockResolvedValue({ data: { message: { ok: 1 } } });
    await expect(apiCall('huf.x.y', { a: { b: 1 } }, { verb: 'GET' })).resolves.toEqual({ ok: 1 });
    const cfg = request.mock.calls[0][0];
    expect(cfg.url).toBe('/api/method/huf.x.y');
    expect(cfg.method).toBe('GET');
    expect(cfg.params.toString()).toBe('a=%7B%22b%22%3A1%7D');
    expect(cfg.data).toBeUndefined();
  });

  it('POST sends JSON body, defaults to POST', async () => {
    request.mockResolvedValue({ data: { message: 5 } });
    await expect(apiCall('huf.x.y', { a: 1 })).resolves.toBe(5);
    expect(request.mock.calls[0][0]).toMatchObject({ method: 'POST', data: { a: 1 } });
  });

  it('throws ApiError for envelope errors', async () => {
    request.mockResolvedValue({ data: { message: { success: false, error: 'no_account' } } });
    await expect(apiCall('m')).rejects.toMatchObject({ name: 'ApiError', code: 'no_account' });
  });

  it('throws normalized HTTP errors without retrying POST', async () => {
    request.mockRejectedValue(axiosErr(500, { exc_type: 'ValidationError' }));
    await expect(apiCall('m')).rejects.toMatchObject({ code: 'ValidationError', httpStatus: 500 });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('times out', async () => {
    request.mockImplementation((cfg: { signal: AbortSignal }) => new Promise((_r, rej) => {
      cfg.signal.addEventListener('abort', () => rej({ name: 'CanceledError', code: 'ERR_CANCELED' }));
    }));
    const p = apiCall('m', {}, { timeoutMs: 100 });
    const assertion = expect(p).rejects.toMatchObject({ code: 'timeout' });
    await vi.advanceTimersByTimeAsync(101);
    await assertion;
  });

  it('aborts via caller signal', async () => {
    request.mockImplementation((cfg: { signal: AbortSignal }) => new Promise((_r, rej) => {
      cfg.signal.addEventListener('abort', () => rej({ name: 'CanceledError', code: 'ERR_CANCELED' }));
    }));
    const ac = new AbortController();
    const p = apiCall('m', {}, { signal: ac.signal, verb: 'GET' });
    const assertion = expect(p).rejects.toMatchObject({ code: 'aborted' });
    ac.abort();
    await assertion;
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('retries GET on network error then succeeds, with backoff', async () => {
    request
      .mockRejectedValueOnce(axiosErr(undefined))
      .mockRejectedValueOnce(axiosErr(503, {}))
      .mockResolvedValue({ data: { message: 'done' } });
    const p = apiCall('m', {}, { verb: 'GET' });
    await vi.advanceTimersByTimeAsync(0);
    expect(request).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(200);
    expect(request).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(400);
    await expect(p).resolves.toBe('done');
    expect(request).toHaveBeenCalledTimes(3);
  });

  it('does not retry GET on 4xx or envelope errors', async () => {
    request.mockRejectedValue(axiosErr(404, { error: { code: 'nf', message: 'x' } }));
    await expect(apiCall('m', {}, { verb: 'GET' })).rejects.toMatchObject({ code: 'nf' });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('gives up after retries', async () => {
    request.mockRejectedValue(axiosErr(undefined));
    const p = apiCall('m', {}, { verb: 'GET', retries: 1 });
    const assertion = expect(p).rejects.toMatchObject({ code: 'network_error' });
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
    expect(request).toHaveBeenCalledTimes(2);
  });
});
