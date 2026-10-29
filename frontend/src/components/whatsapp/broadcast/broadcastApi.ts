import { apiCall, isApiError } from '@/lib/api';
import type { WhatsAppResult } from '@/services/whatsappApi';

const WRITE = 'huf.ai.whatsapp.broadcast.api';
const READ = 'huf.ai.whatsapp.broadcast.api_read';
const READ_METHODS = new Set(['list_broadcasts', 'get_broadcast', 'get_broadcast_template_params', 'list_broadcast_recipients']);

async function broadcastCall<T>(method: string, args: Record<string, unknown>, verb: 'get' | 'post'): Promise<WhatsAppResult<T>> {
  const path = `${READ_METHODS.has(method) ? READ : WRITE}.${method}`;
  try {
    const out = await apiCall<Record<string, unknown> | null>(path, args, { verb: verb === 'get' ? 'GET' : 'POST' });
    return { ...(out && typeof out === 'object' ? out : {}), success: true } as WhatsAppResult<T>;
  } catch (e) {
    return { success: false, error: isApiError(e) ? e.code : 'request_failed', message: e instanceof Error ? e.message : 'Request failed.' };
  }
}

// ---- Broadcast ------------------------------------------------------------

export type BroadcastStatus = 'Draft' | 'Scheduled' | 'Queued' | 'Running' | 'Paused' | 'Completed' | 'Cancelled' | 'Failed';
export type BroadcastRecipientStatus =
  'queued' | 'sending' | 'sent' | 'delivered' | 'read' | 'failed' | 'deferred' | 'unknown' | 'skipped';

export type BroadcastSendVia = 'messages' | 'marketing_messages';

export interface Broadcast {
  name: string;
  title: string;
  status: BroadcastStatus;
  pause_reason?: string | null;
  gateway: string;
  template?: string;
  template_name?: string;
  language_code?: string;
  category?: string;
  send_via?: BroadcastSendVia;
  consent_source?: string | null;
  consent_attested?: number;
  max_recipients?: number | null;
  mps?: number | null;
  scheduled_at?: string | null;
  started_by?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  creation?: string;
  total: number;
  queued: number;
  sending: number;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  deferred: number;
  unknown: number;
  skipped: number;
}

export interface BroadcastRecipient {
  name: string;
  recipient: string;
  status: BroadcastRecipientStatus;
  skip_reason?: string | null;
  error_code?: number | null;
  error_message?: string | null;
  attempts?: number;
  sent_at?: string | null;
  delivered_at?: string | null;
  read_at?: string | null;
  failed_at?: string | null;
}

export interface BroadcastCost {
  currency: string;
  total: number | null;
  by_country: Record<string, { count: number; rate: number | null; subtotal: number | null }>;
  category?: string | null;
  basis?: string;
  rates_verified?: boolean;
  warnings?: string[];
  disclaimer?: string;
}

/** UI view of preview_broadcast. `queued` is the integer the operator must type to confirm. */
export interface BroadcastPreview {
  status?: string;
  consent_attested: boolean;
  recipients: number;
  queued: number;
  skipped: number;
  category?: string | null;
  template_status?: string | null;
  within_limit: boolean | null;
  remaining_24h: number | null;
  warnings: BroadcastIssue[];
  blocking: BroadcastIssue[];
  /** Keys (see get_broadcast_limits) of the limits that affected this broadcast. */
  limits_in_effect: string[];
  cost: BroadcastCost | null;
  confirm_required: boolean;
}

/** A blocking reason or an overridable warning. `code` is what start_broadcast's override_warnings takes. */
export interface BroadcastIssue { code: string; message: string; limit_key?: string | null }

/** Contract items are `{code,message,limit_key}`; a bare string is tolerated and used as both code and message. */
export function toIssue(x: unknown): BroadcastIssue {
  if (typeof x === 'string') return { code: x, message: x, limit_key: null };
  const o = (x ?? {}) as Partial<BroadcastIssue>;
  return { code: String(o.code ?? o.message ?? ''), message: String(o.message ?? o.code ?? ''), limit_key: o.limit_key ?? null };
}

export interface BroadcastRecipientInput {
  recipient: string;
  params?: Record<string, unknown>;
  consent_source?: string;
  consent_at?: string;
}

export interface AddRecipientsResult {
  added: number;
  skipped: { recipient: string; reason: string }[];
  invalid: { recipient?: string; reason?: string }[];
  /** True totals; `skipped`/`invalid` lists are truncated server-side. */
  skippedTotal: number;
  invalidTotal: number;
}

export interface CreateBroadcastInput {
  gateway: string;
  template: string;
  title: string;
  language_code?: string;
  send_via?: BroadcastSendVia;
  body_params?: unknown;
  header_params?: unknown;
  button_params?: unknown;
  consent_source?: string;
  max_recipients?: number;
  mps?: number;
}

// ---- Broadcast response adapters (backend shapes -> UI shapes) -------------

const COUNT_FIELDS = ['total', 'queued', 'sending', 'sent', 'delivered', 'read', 'failed', 'deferred', 'unknown', 'skipped'] as const;

/** Backend `_broadcast_view` (counts nested under `counts`) -> flat UI `Broadcast`. */
export function adaptBroadcast(view: Record<string, unknown>): Broadcast {
  const { counts, ...doc } = view as { counts?: Record<string, number> } & Record<string, unknown>;
  const flat: Record<string, unknown> = { ...doc };
  flat.send_via = doc.send_via === 'marketing_messages' ? 'marketing_messages' : 'messages';
  for (const k of COUNT_FIELDS) flat[k] = Number(counts?.[k] ?? 0);
  return flat as unknown as Broadcast;
}

/** Backend `preview_broadcast` payload -> UI `BroadcastPreview`. */
export function adaptPreview(r: Record<string, any>): BroadcastPreview {
  const l = r.limits ?? {};
  return {
    status: r.status,
    consent_attested: !!r.consent_attested,
    recipients: Number(l.recipients ?? 0),
    queued: Number(r.queued ?? 0),
    skipped: Number(l.skipped ?? 0),
    category: l.category ?? null,
    template_status: l.template_status ?? null,
    within_limit: l.within_limit ?? null,
    remaining_24h: l.remaining_24h ?? null,
    warnings: (Array.isArray(l.warnings) ? l.warnings : []).map(toIssue),
    blocking: (Array.isArray(l.blocking) ? l.blocking : []).map(toIssue),
    limits_in_effect: (Array.isArray(r.limits_in_effect) ? r.limits_in_effect : Array.isArray(l.limits_in_effect) ? l.limits_in_effect : []).map(String),
    cost: r.cost ?? null,
    confirm_required: !!r.confirm_required,
  };
}

/** `invalid` entries are `{recipient, reason}`; tolerate bare strings. */
export function adaptAddResult(r: { added?: number; skipped?: unknown[]; invalid?: unknown[]; skipped_total?: number; invalid_total?: number }): AddRecipientsResult {
  const norm = (x: unknown) => (typeof x === 'string' ? { recipient: x } : (x as { recipient?: string; reason?: string }));
  const skipped = (r.skipped ?? []).map((x) => ({ recipient: '', reason: '', ...norm(x) }));
  const invalid = (r.invalid ?? []).map(norm);
  return {
    added: Number(r.added ?? 0),
    skipped,
    invalid,
    skippedTotal: Math.max(Number(r.skipped_total ?? 0) || 0, skipped.length),
    invalidTotal: Math.max(Number(r.invalid_total ?? 0) || 0, invalid.length),
  };
}

async function mapOk<T, U>(p: Promise<WhatsAppResult<T>>, f: (v: T) => U): Promise<WhatsAppResult<U>> {
  const res = await p;
  return res.success ? ({ ...f(res as T), success: true } as WhatsAppResult<U>) : res;
}

type Mutated = { broadcast?: string; status?: string };

export const createBroadcast = (input: CreateBroadcastInput) =>
  broadcastCall<{ broadcast: string; status: string; category?: string | null }>(
    'create_broadcast',
    {
      ...input,
      body_params: input.body_params === undefined ? undefined : JSON.stringify(input.body_params),
      header_params: input.header_params === undefined ? undefined : JSON.stringify(input.header_params),
      button_params: input.button_params === undefined ? undefined : JSON.stringify(input.button_params),
    },
    'post',
  );

export interface BroadcastTemplateVariable { name?: string; index?: number; sample?: string }
export interface BroadcastTemplateParams {
  parameter_format: 'NAMED' | 'POSITIONAL';
  body: BroadcastTemplateVariable[];
  header: BroadcastTemplateHeader | null;
  buttons: BroadcastTemplateButton[];
}
export interface BroadcastTemplateHeader { type: string; required: boolean; name?: string; index?: number; sample?: string | null }
export interface BroadcastTemplateButton { index: number; sub_type: 'url' | 'copy_code' | 'quick_reply'; required: boolean; label?: string | null }

export const getBroadcastTemplateParams = (gateway: string, template: string) =>
  mapOk(
    broadcastCall<Partial<BroadcastTemplateParams>>('get_broadcast_template_params', { gateway, template }, 'get'),
    (r): BroadcastTemplateParams => ({
      parameter_format: r.parameter_format === 'NAMED' ? 'NAMED' : 'POSITIONAL',
      body: Array.isArray(r.body) ? r.body : [],
      header: r.header ?? null,
      buttons: Array.isArray(r.buttons) ? r.buttons : [],
    }),
  );

export const addBroadcastRecipients = (broadcast: string, opts: { recipients?: BroadcastRecipientInput[]; csvText?: string }) =>
  mapOk(
    broadcastCall<AddRecipientsResult>(
      'add_broadcast_recipients',
      {
        broadcast,
        ...(opts.recipients ? { recipients: JSON.stringify(opts.recipients) } : {}),
        ...(opts.csvText !== undefined ? { csv_text: opts.csvText } : {}),
      },
      'post',
    ),
    adaptAddResult,
  );

export const attestBroadcastConsent = (broadcast: string, consentSource: string) =>
  broadcastCall<{ broadcast?: string; consent_attested?: boolean; consent_source?: string }>(
    'attest_broadcast_consent', { broadcast, consent_source: consentSource }, 'post');

export const previewBroadcast = (broadcast: string) =>
  mapOk(broadcastCall<Record<string, any>>('preview_broadcast', { broadcast }, 'post'), (r) => ({ preview: adaptPreview(r) }));

/** `overrideWarnings` = codes of the warnings the operator acknowledged; the server rejects the start (`warnings_changed`) if they no longer match. */
export const startBroadcast = (broadcast: string, confirmCount: string | number, overrideWarnings: string[] = []) =>
  broadcastCall<Mutated & { queued?: number; warnings?: unknown[] }>(
    'start_broadcast', { broadcast, confirm_count: String(confirmCount), override_warnings: JSON.stringify(overrideWarnings) }, 'post');

/** `scheduledAt` is 'YYYY-MM-DD HH:mm:ss' in the SITE timezone. */
export const scheduleBroadcast = (broadcast: string, scheduledAt: string, confirmCount: string | number, overrideWarnings: string[] = []) =>
  broadcastCall<Mutated & { scheduled_at?: string }>(
    'schedule_broadcast', { broadcast, scheduled_at: scheduledAt, confirm_count: String(confirmCount), override_warnings: JSON.stringify(overrideWarnings) }, 'post');
export const unscheduleBroadcast = (broadcast: string) => broadcastCall<Mutated>('unschedule_broadcast', { broadcast }, 'post');
/** Creates a new Draft with the retryable failed recipients; returns its name in `broadcast`. */
export const retryFailedRecipients = (broadcast: string) =>
  broadcastCall<{ broadcast?: string; retried_from?: string; added?: number }>('retry_failed_recipients', { broadcast }, 'post');

export const pauseBroadcast = (broadcast: string) => broadcastCall<Mutated>('pause_broadcast', { broadcast }, 'post');
export const resumeBroadcast = (broadcast: string) => broadcastCall<Mutated>('resume_broadcast', { broadcast }, 'post');
export const cancelBroadcast = (broadcast: string) => broadcastCall<Mutated>('cancel_broadcast', { broadcast }, 'post');
export const removeBroadcastRecipient = (broadcast: string, recipient: string) =>
  broadcastCall<{ broadcast?: string; removed?: number; queued?: number }>('remove_broadcast_recipient', { broadcast, recipient }, 'post');
export const deleteBroadcast = (broadcast: string) =>
  broadcastCall<{ broadcast?: string; deleted?: boolean }>('delete_broadcast', { broadcast }, 'post');
export const pauseAllBroadcasts = (gateway: string) => broadcastCall<{ gateway?: string; paused?: string[] }>('pause_all_broadcasts', { gateway }, 'post');

export const listBroadcasts = (opts: { gateway?: string; status?: string; limit?: number; offset?: number } = {}) =>
  mapOk(broadcastCall<{ broadcasts: Record<string, unknown>[] }>('list_broadcasts', opts, 'get'),
    (r) => ({ broadcasts: (r.broadcasts ?? []).map(adaptBroadcast) }));

export const getBroadcast = (broadcast: string) =>
  mapOk(broadcastCall<{ broadcast: Record<string, unknown> }>('get_broadcast', { broadcast }, 'get'),
    (r) => ({ broadcast: adaptBroadcast(r.broadcast) }));

export const listBroadcastRecipients = (broadcast: string, opts: { status?: string; limit?: number; offset?: number } = {}) =>
  broadcastCall<{ recipients: BroadcastRecipient[] }>('list_broadcast_recipients', { broadcast, ...opts }, 'get');
