/**
 * Telegram Mini App API client (token auth, no Frappe session).
 * Contract: docs/gateways/telegram-miniapp-api.md. The token lives in module memory only.
 */

const METHOD_BASE = '/api/method/huf.ai.telegram_miniapp_api.';
const AUTH_METHOD = '/api/method/huf.ai.telegram_admin.telegram_miniapp_auth';
const TOKEN_HEADER = 'X-Huf-Tg-Token';

export type RoleScope = string;

export interface TgAuthResult {
  token: string;
  expires_in: number;
  role_scope: RoleScope;
  gateway: string;
}
export interface TgMe {
  frappe_user: string;
  full_name: string;
  role_scope: RoleScope;
  gateway: string;
  telegram_user_id: string | number;
}
export interface TgDoctypeChoice { name: string }
export interface TgConfig {
  gateway: string;
  bot_name?: string;
  role_scope: RoleScope;
  session_ttl?: number;
  confirm_ttl?: number;
  limits?: { search_max?: number; audit_max?: number };
  features?: Partial<Record<'search' | 'approvals' | 'digest' | 'act' | 'audit' | 'audit_all', boolean>>;
  /** Record types the signed-in user may search (permission-filtered and capped by the server). */
  doctypes: TgDoctypeChoice[];
}
export interface TgSearchItem { name: string; title?: string }
export interface TgSearchResult { doctype: string; items: TgSearchItem[] }
export interface TgDocField { fieldname: string; label: string; fieldtype: string; value: unknown }
export interface TgDocSummary {
  doctype: string;
  name: string;
  title?: string;
  workflow_state?: string | null;
  status?: string | null;
  docstatus?: number;
  modified?: string;
  fields: TgDocField[];
  actions: string[];
  desk_url?: string;
}
export interface TgApprovalItem { doctype: string; name: string; state?: string; actions: string[] }
export interface TgActPrepare {
  nonce: string;
  description: string;
  expires_in: number;
  action: { doctype: string; name: string; action: string };
}
export interface TgDigest {
  text: string;
  approvals: { doctype: string; name: string; state?: string }[];
  actions_24h: number;
}
export interface TgAuditItem {
  action: string;
  frappe_user: string;
  reference_doctype?: string;
  reference_name?: string;
  result: string;
  creation: string;
}
export interface TgAudit { scope: 'own' | 'all'; items: TgAuditItem[] }

export type TgErrorCode =
  | 'unauthorized' | 'permission_denied' | 'not_found' | 'invalid'
  | 'refused' | 'rate_limited' | 'internal' | 'network';

export class TelegramAppError extends Error {
  code: TgErrorCode;
  status: number;
  constructor(code: TgErrorCode, message: string, status = 0) {
    super(message);
    this.name = 'TelegramAppError';
    this.code = code;
    this.status = status;
  }
}

let token: string | null = null;
let authContext: { initData: string; gateway: string } | null = null;
let reauthInFlight: Promise<TgAuthResult> | null = null;

export function getToken(): string | null { return token; }
export function resetTelegramAppSession(): void {
  token = null;
  authContext = null;
  reauthInFlight = null;
}

const STATUS_CODES: Record<number, TgErrorCode> = {
  400: 'invalid', 401: 'unauthorized', 403: 'permission_denied',
  404: 'not_found', 429: 'rate_limited', 500: 'internal',
};

/** Parse a Frappe response body + HTTP status into data or a TelegramAppError. */
export function parseEnvelope<T>(body: unknown, status: number): T {
  const message = (body as { message?: unknown } | null)?.message;
  const env = message as { ok?: boolean; data?: T; error?: { code?: string; message?: string } } | undefined;
  if (env && typeof env === 'object' && env.ok === true) return env.data as T;
  if (env && typeof env === 'object' && env.ok === false) {
    const code = (env.error?.code as TgErrorCode) || STATUS_CODES[status] || 'internal';
    throw new TelegramAppError(code, env.error?.message || 'Request failed.', status);
  }
  throw new TelegramAppError(STATUS_CODES[status] || 'internal', 'Request failed.', status);
}

async function readJson(res: Response): Promise<unknown> {
  try { return await res.json(); } catch { return null; }
}

/** Exchange Telegram initData for a token (kept in memory only). */
export async function authenticate(initData: string, gateway: string): Promise<TgAuthResult> {
  authContext = { initData, gateway };
  let res: Response;
  try {
    res = await fetch(AUTH_METHOD, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      credentials: 'omit',
      body: JSON.stringify({ init_data: initData, gateway }),
    });
  } catch {
    throw new TelegramAppError('network', 'Network error. Check your connection.');
  }
  const body = await readJson(res);
  const msg = (body as { message?: Partial<TgAuthResult> } | null)?.message;
  if (res.ok && msg && typeof msg.token === 'string' && msg.token) {
    token = msg.token;
    return msg as TgAuthResult;
  }
  // The auth endpoint raises (no envelope) on failure; keep the message generic.
  throw new TelegramAppError(
    res.status === 429 ? 'rate_limited' : 'unauthorized',
    res.status === 429 ? 'Too many attempts. Try again shortly.' : 'Could not sign in from Telegram.',
    res.status,
  );
}

function reauth(): Promise<TgAuthResult> {
  if (!authContext) {
    return Promise.reject(new TelegramAppError('unauthorized', 'Session expired. Reopen the app from Telegram.', 401));
  }
  if (!reauthInFlight) {
    reauthInFlight = authenticate(authContext.initData, authContext.gateway).finally(() => {
      reauthInFlight = null;
    });
  }
  return reauthInFlight;
}

async function rawCall<T>(name: string, params: Record<string, unknown>): Promise<T> {
  // Always POST with the token in the header: a token must never travel in a URL (access logs, Referer).
  const headers: Record<string, string> = { Accept: 'application/json', 'Content-Type': 'application/json' };
  if (token) headers[TOKEN_HEADER] = token;
  const url = METHOD_BASE + name;
  const init: RequestInit = { method: 'POST', headers, credentials: 'omit', body: JSON.stringify(params) };
  let res: Response;
  try { res = await fetch(url, init); } catch {
    throw new TelegramAppError('network', 'Network error. Check your connection.');
  }
  return parseEnvelope<T>(await readJson(res), res.status);
}

/** Call an endpoint; on 401 re-authenticate once with the stored initData and retry. */
export async function call<T>(name: string, params: Record<string, unknown> = {}): Promise<T> {
  try {
    return await rawCall<T>(name, params);
  } catch (e) {
    if (e instanceof TelegramAppError && e.code === 'unauthorized') {
      token = null;
      await reauth();
      return rawCall<T>(name, params);
    }
    throw e;
  }
}

export const me = () => call<TgMe>('me');
export const getConfig = () => call<TgConfig>('config');
export const search = (doctype: string, text = '', limit = 10) =>
  call<TgSearchResult>('search', { doctype, text, limit });
export const getDocSummary = (doctype: string, name: string) =>
  call<TgDocSummary>('get_doc_summary', { doctype, name });
export const approvals = () => call<{ items: TgApprovalItem[] }>('approvals');
export const actPrepare = (doctype: string, name: string, action: string) =>
  call<TgActPrepare>('act_prepare', { doctype, name, action });
export const actConfirm = (nonce: string) => call<{ result: string }>('act_confirm', { nonce });
export const digest = () => call<TgDigest>('digest');
export const audit = (limit = 20) => call<TgAudit>('audit', { limit });
export async function revokeToken(): Promise<void> {
  try { await call<{ revoked: boolean }>('revoke_token', {}); } finally { resetTelegramAppSession(); }
}
