/**
 * Single backend call client for Huf.
 *
 * Built on the same axios instance as `frappe-sdk` (`frappe.axios`), so session
 * cookies, the CSRF header and the CSRF-retry / session-invalidation
 * interceptors apply unchanged. Adds: one place for the `/api/method/` prefix,
 * envelope unwrapping, one typed error (`ApiError`) for every error shape the
 * backend produces, timeout / abort support and safe retries for GETs.
 */
import type { AxiosRequestConfig } from 'axios';
import { frappe } from '@/lib/frappe-sdk';
import { extractFrappeServerMessages, getFrappeErrorMessage } from '@/lib/frappe-error';

/** The only place the whitelisted-method URL prefix is spelled out. */
export const API_METHOD_PREFIX = '/api/method/';

export type ApiVerb = 'GET' | 'POST';
export type ApiArgs = Record<string, unknown>;

export type ApiErrorCode = 'network_error' | 'timeout' | 'aborted' | (string & {});

export interface ApiOptions {
  /** Default 'POST'. GET args are sent as query params (objects JSON-stringified). */
  verb?: ApiVerb;
  signal?: AbortSignal;
  /** Per-attempt timeout in ms. Default 60000; 0 disables. */
  timeoutMs?: number;
  /** Extra attempts after the first. Only honoured for GET (default 2); POST never retries. */
  retries?: number;
}

export class ApiError extends Error {
  readonly name = 'ApiError';
  readonly code: ApiErrorCode;
  /** Status carried inside the body (v1 `error.status`, Frappe `http_status_code`), if any. */
  readonly status?: number;
  /** HTTP response status, if a response was received. */
  readonly httpStatus?: number;
  /** The original thrown value / response body. */
  readonly raw: unknown;

  constructor(init: { code: ApiErrorCode; message: string; status?: number; httpStatus?: number; raw?: unknown }) {
    super(init.message);
    this.code = init.code;
    this.status = init.status;
    this.httpStatus = init.httpStatus;
    this.raw = init.raw;
  }
}

export const isApiError = (e: unknown): e is ApiError => e instanceof ApiError;

const DEFAULT_TIMEOUT_MS = 60_000;
const DEFAULT_GET_RETRIES = 2;
const BACKOFF_BASE_MS = 200;

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => !!v && typeof v === 'object' && !Array.isArray(v);
const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);

/** Build an ApiError from an error *body* (not a thrown transport error); null if it is not an error body. */
function errorFromBody(body: unknown, httpStatus?: number): ApiError | null {
  if (typeof body === 'string') return null;
  if (!isRec(body)) return null;

  // v1 contract: {error: {code, message}}
  if (isRec(body.error)) {
    const e = body.error;
    return new ApiError({
      code: typeof e.code === 'string' && e.code ? e.code : 'error',
      message: typeof e.message === 'string' && e.message ? e.message : 'Request failed.',
      status: num(e.status),
      httpStatus,
      raw: body,
    });
  }

  // Management envelope: {success: false, error: <code>, message?}
  if ((body.success === false || (typeof body.error === 'string' && body.error)) && body.success !== true) {
    const code = typeof body.error === 'string' && body.error ? body.error : 'unknown_error';
    const message = typeof body.message === 'string' && body.message ? body.message : code;
    return new ApiError({ code, message, httpStatus, raw: body });
  }

  // Frappe: exc_type / exc / exception / _server_messages
  if (body.exc_type || body.exc || body.exception || body._server_messages) {
    const code = typeof body.exc_type === 'string' && body.exc_type
      ? body.exc_type
      : typeof body.exception === 'string'
        ? (body.exception.split('.').pop()?.split(':')[0]?.split('(')[0] || 'frappe_error')
        : 'frappe_error';
    const hasMsgs = (extractFrappeServerMessages(body)?.length ?? 0) > 0;
    const message = hasMsgs || body.exception
      ? getFrappeErrorMessage(body)
      : 'The server reported an error.';
    return new ApiError({ code, message, status: num(body.http_status_code), httpStatus, raw: body });
  }
  return null;
}

/** Convert anything thrown (or any error body) into an ApiError. Never throws. */
export function normalizeError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;

  if (typeof err === 'string') {
    return new ApiError({ code: 'error', message: err || 'An unexpected error occurred.', raw: err });
  }

  if (isRec(err)) {
    const name = typeof err.name === 'string' ? err.name : '';
    const ecode = typeof err.code === 'string' ? err.code : '';

    if (name === 'AbortError' || name === 'CanceledError' || ecode === 'ERR_CANCELED') {
      return new ApiError({ code: 'aborted', message: 'The request was cancelled.', raw: err });
    }
    if (name === 'TimeoutError' || ecode === 'ECONNABORTED' || ecode === 'ETIMEDOUT') {
      return new ApiError({ code: 'timeout', message: 'The request timed out.', raw: err });
    }

    // Axios-style error with an HTTP response
    const response = isRec(err.response) ? err.response : undefined;
    if (response) {
      const httpStatus = num(response.status);
      const fromBody = errorFromBody(response.data, httpStatus) ?? errorFromBody(err.response, httpStatus);
      if (fromBody) return new ApiError({ code: fromBody.code, message: fromBody.message, status: fromBody.status, httpStatus, raw: err });
      const text = typeof response.data === 'string' && response.data.length < 300 ? response.data : '';
      return new ApiError({
        code: httpStatus ? `http_${httpStatus}` : 'error',
        message: text || (typeof err.message === 'string' && err.message) || `Request failed (${httpStatus ?? 'unknown'}).`,
        httpStatus,
        raw: err,
      });
    }

    // Axios with a request but no response, or fetch TypeError: network failure
    if (ecode === 'ERR_NETWORK' || (err.isAxiosError === true && err.request !== undefined) || /failed to fetch|network ?error|load failed/i.test(String(err.message))) {
      return new ApiError({ code: 'network_error', message: 'Cannot reach the server. Check your connection.', raw: err });
    }

    // A bare error body (e.g. a response body passed straight in)
    const fromBody = errorFromBody(err);
    if (fromBody) return fromBody;

    // SDK-wrapped Frappe errors keep details under data / originalError
    if (isRec(err.data)) {
      const d = errorFromBody(err.data);
      if (d) return d;
    }
    if (err instanceof Error || typeof err.message === 'string') {
      return new ApiError({ code: 'error', message: getFrappeErrorMessage(err), raw: err });
    }
  }

  return new ApiError({ code: 'error', message: 'An unexpected error occurred. Please try again.', raw: err });
}

/**
 * Return the payload of a response, removing Frappe's `{message: ...}` envelope.
 * Throws ApiError for the management `{success:false,error}` and v1 `{error:{code,message}}` envelopes
 * (checked both before and after unwrapping `message`).
 */
export function unwrapEnvelope<T = unknown>(res: unknown): T {
  const outer = errorFromBody(res);
  if (outer) throw outer;
  const value = isRec(res) && 'message' in res ? res.message : res;
  if (value !== res) {
    const inner = errorFromBody(value);
    if (inner) throw inner;
  }
  return value as T;
}

/** Full URL path for a whitelisted method (accepts an already-prefixed path). */
export function methodUrl(method: string): string {
  return method.startsWith(API_METHOD_PREFIX) ? method : `${API_METHOD_PREFIX}${method}`;
}

/** Query params for GET calls: null/undefined dropped, objects JSON-stringified. */
export function toQueryParams(args?: ApiArgs): URLSearchParams {
  const params = new URLSearchParams();
  if (!args) return params;
  for (const [k, v] of Object.entries(args)) {
    if (v === null || v === undefined) continue;
    params.set(k, typeof v === 'object' ? JSON.stringify(v) : String(v));
  }
  return params;
}

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(normalizeError({ name: 'AbortError' }));
    const t = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(t);
      reject(normalizeError({ name: 'AbortError' }));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });

async function attempt(method: string, args: ApiArgs | undefined, o: Required<Pick<ApiOptions, 'verb'>> & ApiOptions): Promise<unknown> {
  const controller = new AbortController();
  let timedOut = false;
  const onOuterAbort = () => controller.abort();
  if (o.signal) {
    if (o.signal.aborted) controller.abort();
    else o.signal.addEventListener('abort', onOuterAbort, { once: true });
  }
  const timeoutMs = o.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timer = timeoutMs > 0 ? setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs) : undefined;

  const config: AxiosRequestConfig = { url: methodUrl(method), method: o.verb, signal: controller.signal };
  if (o.verb === 'GET') config.params = toQueryParams(args);
  else config.data = args ?? {};

  try {
    const res = await frappe.axios.request(config);
    return res.data;
  } catch (err) {
    if (timedOut) throw new ApiError({ code: 'timeout', message: 'The request timed out.', raw: err });
    throw normalizeError(err);
  } finally {
    if (timer) clearTimeout(timer);
    o.signal?.removeEventListener('abort', onOuterAbort);
  }
}

const isRetryable = (e: ApiError) =>
  e.code === 'network_error' || e.code === 'timeout' || (e.httpStatus !== undefined && e.httpStatus >= 500);

/**
 * Call a whitelisted backend method and return its unwrapped payload.
 * Throws ApiError on any failure. Only GET requests are retried (network / timeout / 5xx).
 */
export async function apiCall<T = unknown>(method: string, args?: ApiArgs, opts: ApiOptions = {}): Promise<T> {
  const verb: ApiVerb = opts.verb ?? 'POST';
  const retries = verb === 'GET' ? (opts.retries ?? DEFAULT_GET_RETRIES) : 0;
  for (let n = 0; ; n++) {
    try {
      const body = await attempt(method, args, { ...opts, verb });
      return unwrapEnvelope<T>(body);
    } catch (e) {
      const err = normalizeError(e);
      if (n >= retries || !isRetryable(err) || opts.signal?.aborted) throw err;
      await sleep(BACKOFF_BASE_MS * 2 ** n, opts.signal);
    }
  }
}
