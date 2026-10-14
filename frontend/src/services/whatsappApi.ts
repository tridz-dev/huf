import { call, file } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

const BASE = 'huf.ai.whatsapp_management';

export const TEMPLATE_NAME_RE = /^[a-z0-9_]+$/;
export const TEMPLATE_NAME_MAX = 512;
export const TEMPLATE_CATEGORIES = ['MARKETING', 'UTILITY'] as const;
export type TemplateCategory = (typeof TEMPLATE_CATEGORIES)[number];

export interface FieldError {
  field: string;
  code: string;
  message: string;
}

export interface WhatsAppError {
  success: false;
  error: string;
  message?: string;
  hint?: string;
  expires_at?: string | null;
  /** Present for `validation_failed`: every problem found, per field. */
  errors?: FieldError[];
  /** Draft approval: the status the draft ended in and why Meta refused it. */
  status?: string;
  submit_error?: string;
}
export type WhatsAppResult<T> = ({ success: true } & T) | WhatsAppError;

export interface WhatsAppAccount {
  name: string;
  phone_id?: string;
  status?: string;
}

export interface GatewayStatus {
  name: string;
  enabled: boolean;
  whatsapp_account?: string | null;
  phone_number_id?: string;
  fallback_template?: string | null;
  app_secret_present: boolean;
  app_secret_missing: boolean;
  verify_token_present: boolean;
  account_phone_mismatch?: boolean;
  webhook_url: string;
  callback_warning: string;
  failing_checks: string[];
}

export interface SetupStatus {
  bridge_available: boolean;
  accounts: WhatsAppAccount[];
  gateways: GatewayStatus[];
  callback_warning: string;
}

export interface WhatsAppTemplate {
  name: string;
  template_name: string;
  actual_name?: string;
  category?: string;
  language_code?: string;
  status?: string;
  id?: string;
  whatsapp_account?: string;
  template?: string;
  header_type?: HeaderType | '';
  header?: string;
  footer?: string;
  sample_values?: string;
  buttons?: { button_type: string; button_label?: string; url_type?: string; website_url?: string; phone_number?: string }[];
  rejected_reason?: string;
  quality_score?: string;
  correct_category?: string;
  category_change_pending?: boolean;
  last_meta_update?: string | null;
}

export interface TemplateDetail {
  name: string;
  template_id: string;
  template_name: string;
  language_code: string;
  category: string;
  correct_category: string;
  category_change_pending: boolean;
  status: string;
  whatsapp_account?: string;
  components: {
    header: { type: HeaderType; text: string; sample: string } | null;
    body: { text: string; sample_values: string[] };
    footer: { text: string } | null;
    buttons: TemplateButton[];
  };
  state: {
    rejected_reason: string;
    rejection_recommendation: string;
    other_info: string;
    quality_score: string;
    last_event: string;
    last_event_at: string | null;
    last_meta_update: string | null;
  };
  editable: boolean;
  editable_reason?: string;
  editable_message?: string;
  edits_left?: number | null;
  next_edit_at?: string | null;
  manager_url: string;
  business_id: string;
}

export type DraftStatus = 'Draft' | 'Pending Review' | 'Failed' | 'Approved & Submitted' | 'Rejected';
export interface TemplateDraft {
  name: string;
  template_name: string;
  language_code: string;
  category: string;
  whatsapp_account?: string;
  status: DraftStatus | string;
  payload: Partial<TemplatePayload>;
  requested_by?: string;
  requested_via?: 'User' | 'Agent run' | string;
  agent_run?: string;
  reviewed_by?: string;
  reviewed_at?: string | null;
  review_note?: string;
  submitted_template?: string;
  submit_error?: string;
  creation?: string | null;
}

export const TEMPLATE_LIMITS = { body: 1024, header: 60, footer: 60, button: 25, quickReplies: 3, cta: 2 } as const;
export const HEADER_TYPES = ['TEXT', 'IMAGE', 'DOCUMENT'] as const;
export type HeaderType = (typeof HEADER_TYPES)[number];
export const MEDIA_KINDS = ['image', 'document', 'audio', 'video'] as const;
export type MediaKind = (typeof MEDIA_KINDS)[number];

export type TemplateButtonType = 'QUICK_REPLY' | 'URL' | 'PHONE_NUMBER';
export interface TemplateButton {
  type: TemplateButtonType;
  text: string;
  url?: string;
  example?: string;
  phone_number?: string;
}

export interface TemplatePayload {
  template_name: string;
  category: TemplateCategory;
  language_code: string;
  template: string;
  header_type?: HeaderType;
  header?: string;
  /** Header example: a value for a TEXT header variable, or a file URL for IMAGE/DOCUMENT. */
  sample?: string;
  footer?: string;
  sample_values?: string;
  buttons?: TemplateButton[];
}

export type EditTemplatePayload = Omit<TemplatePayload, 'template_name' | 'language_code' | 'header_type'> & {
  header_type?: HeaderType | '';
};

export type HeaderParam = string | { type: 'image' | 'document' | 'video'; link: string; filename?: string };
export interface ButtonParam {
  index: number;
  sub_type: 'url' | 'quick_reply';
  text: string;
}

/** Unwrap the `{message: ...}` envelope; thrown transport errors become error results. */
async function invoke<T>(
  method: string,
  args: Record<string, unknown>,
  verb: 'get' | 'post',
): Promise<WhatsAppResult<T>> {
  try {
    const res = verb === 'post' ? await call.post(`${BASE}.${method}`, args) : await call.get(`${BASE}.${method}`, args);
    return unwrapResult<T>(res);
  } catch (err) {
    return { success: false, error: 'request_failed', message: getFrappeErrorMessage(err) };
  }
}

export function unwrapResult<T>(res: unknown): WhatsAppResult<T> {
  const body = (res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res) as
    | (Partial<WhatsAppError> & { success?: boolean })
    | null
    | undefined;
  if (!body || typeof body !== 'object') {
    return { success: false, error: 'invalid_response', message: 'Unexpected response from server.' };
  }
  if (body.success === false || body.error) {
    return { ...(body as object), success: false, error: body.error || 'unknown_error' } as WhatsAppError;
  }
  return body as WhatsAppResult<T>;
}

export function isBridgeUnavailable(res: { success: boolean; error?: string }): boolean {
  return !res.success && res.error === 'bridge_unavailable';
}

export function errorText(res: WhatsAppError): string {
  const map: Record<string, string> = {
    bridge_unavailable: 'The optional frappe_whatsapp app is not installed on this site.',
    no_account: 'This gateway is not linked to a WhatsApp Account.',
    gateway_required: 'Choose a WhatsApp gateway first.',
    template_name_taken_by_other_account: 'Another WhatsApp account already uses this template name. Choose a different name.',
    template_not_found: 'This template does not belong to the selected gateway.',
    window_closed: 'The 24-hour customer-service window is closed for this number.',
    invalid_recipient: 'Enter a phone number with 7 to 15 digits.',
    invalid_name: 'Template name may only contain lowercase letters, digits and underscores.',
    template_in_use: 'This template has been used in sent messages and cannot be deleted.',
    not_found: 'This template or draft no longer exists.',
    already_processed: 'This draft has already been handled.',
    immutable_field: 'The name and language of a template cannot be changed.',
    edit_limit_24h: 'Approved templates can be edited once every 24 hours.',
    edit_limit_30d: 'The edit limit for the last 30 days has been used up.',
    status_not_editable: 'This template cannot be edited in its current state.',
    no_template_id: 'This template is not linked to WhatsApp yet. Sync templates first.',
  };
  if (res.errors?.length) return res.errors.map((e) => e.message).join(' ');
  return res.message || map[res.error] || res.error;
}

/** Placeholders in order of first appearance, e.g. "Hi {{1}}, {{2}}" -> [1, 2]. */
export function extractPlaceholders(body: string): number[] {
  const seen = new Set<number>();
  for (const m of body.matchAll(/\{\{\s*(\d+)\s*\}\}/g)) seen.add(Number(m[1]));
  return [...seen].sort((a, b) => a - b);
}

export interface TemplateForm {
  name: string;
  category?: TemplateCategory;
  language: string;
  body: string;
  samples: string[];
  headerType?: HeaderType | '';
  header?: string;
  headerSample?: string;
  footer?: string;
  buttons?: TemplateButton[];
  /** Edit mode: a media header with no new sample keeps the file already on the template. */
  keepExistingMedia?: boolean;
}

/** WhatsApp rejects a body that starts or ends with a variable. */
export function bodyVariableEdgeProblem(body: string): string | null {
  const text = body.trim();
  if (/^\{\{\s*\d+\s*\}\}/.test(text)) return 'The message cannot start with a variable. Add some text before {{1}}.';
  if (/\{\{\s*\d+\s*\}\}$/.test(text)) return 'The message cannot end with a variable. Add some text after the last variable.';
  return null;
}

/** Live check of the template name; empty string means nothing to say yet. */
export function templateNameProblem(name: string): string | null {
  if (!name) return null;
  if (!TEMPLATE_NAME_RE.test(name)) return 'Use only lowercase letters, digits and underscores.';
  if (name.length > TEMPLATE_NAME_MAX) return `Names are limited to ${TEMPLATE_NAME_MAX} characters.`;
  return null;
}

export function validateTemplateForm(f: TemplateForm): string | null {
  if (!f.name.trim()) return 'Name is required';
  const nameProblem = templateNameProblem(f.name);
  if (nameProblem) return nameProblem;
  if (!f.language.trim()) return 'Language is required';
  if (!f.body.trim()) return 'Body is required';
  if (f.body.length > TEMPLATE_LIMITS.body) return `Body is limited to ${TEMPLATE_LIMITS.body} characters`;
  const holes = extractPlaceholders(f.body);
  if (holes.some((n, i) => n !== i + 1)) return 'Placeholders must be numbered {{1}}, {{2}}, ... without gaps';
  const edge = bodyVariableEdgeProblem(f.body);
  if (edge) return edge;
  if (holes.length > 0 && f.samples.slice(0, holes.length).some((s) => !s.trim())) {
    return 'Provide a sample value for every placeholder';
  }
  if (f.samples.slice(0, holes.length).some((s) => s.includes(','))) return 'Sample values cannot contain commas';

  if (f.headerType === 'TEXT') {
    const text = f.header ?? '';
    if (!text.trim()) return 'Header text is required';
    if (text.length > TEMPLATE_LIMITS.header) return `Header text is limited to ${TEMPLATE_LIMITS.header} characters`;
    const headerHoles = extractPlaceholders(text);
    if (headerHoles.length > 1 || (headerHoles.length === 1 && headerHoles[0] !== 1)) {
      return 'A text header allows at most one variable, {{1}}';
    }
    if (headerHoles.length === 1 && !(f.headerSample ?? '').trim()) return 'Provide an example for the header variable';
  } else if (f.headerType === 'IMAGE' || f.headerType === 'DOCUMENT') {
    const reuseExisting = f.keepExistingMedia && !(f.headerSample ?? '').trim();
    if (!reuseExisting && !/^https?:\/\//.test((f.headerSample ?? '').trim())) {
      return 'Provide an http(s) link to a sample file for the header';
    }
  }

  const footer = f.footer ?? '';
  if (footer.length > TEMPLATE_LIMITS.footer) return `Footer is limited to ${TEMPLATE_LIMITS.footer} characters`;
  if (footer.includes('{{')) return 'The footer cannot contain variables';

  const buttons = f.buttons ?? [];
  const quick = buttons.filter((b) => b.type === 'QUICK_REPLY').length;
  if (quick > TEMPLATE_LIMITS.quickReplies) return `At most ${TEMPLATE_LIMITS.quickReplies} quick-reply buttons`;
  if (buttons.length - quick > TEMPLATE_LIMITS.cta) return `At most ${TEMPLATE_LIMITS.cta} link or phone buttons`;
  if (buttons.filter((b) => b.type === 'PHONE_NUMBER').length > 1) return 'Only one phone button is allowed';
  const kinds = buttons.map((b) => b.type === 'QUICK_REPLY');
  if (kinds.filter((k, i) => i > 0 && k !== kinds[i - 1]).length > 1) {
    return 'Keep quick-reply buttons together and link/phone buttons together';
  }
  for (const [i, b] of buttons.entries()) {
    const label = `Button ${i + 1}`;
    if (!b.text.trim()) return `${label} needs text`;
    if (b.text.length > TEMPLATE_LIMITS.button) return `${label} text is limited to ${TEMPLATE_LIMITS.button} characters`;
    if (b.type === 'URL') {
      if (!/^https?:\/\//.test(b.url ?? '')) return `${label} needs an http(s) link`;
      if ((b.url ?? '').includes('{{')) {
        if (!(b.url ?? '').endsWith('{{1}}') || (b.url ?? '').split('{{').length > 2) return `${label}: the link may only end with {{1}}`;
        if (!(b.example ?? '').trim()) return `${label} needs an example link`;
      }
    }
    if (b.type === 'PHONE_NUMBER' && !/^\+?[0-9 ()\-.]{7,20}$/.test(b.phone_number ?? '')) {
      return `${label} needs a phone number such as +15551234567`;
    }
  }
  return null;
}

export function buildTemplatePayload(f: TemplateForm & { category: TemplateCategory }): TemplatePayload {
  const count = extractPlaceholders(f.body).length;
  const payload: TemplatePayload = {
    template_name: f.name.trim(),
    category: f.category,
    language_code: f.language.trim(),
    template: f.body,
  };
  if (f.headerType === 'TEXT' && f.header?.trim()) {
    payload.header_type = 'TEXT';
    payload.header = f.header.trim();
    if (f.headerSample?.trim() && extractPlaceholders(f.header).length > 0) payload.sample = f.headerSample.trim();
  } else if (f.headerType === 'IMAGE' || f.headerType === 'DOCUMENT') {
    payload.header_type = f.headerType;
    payload.sample = (f.headerSample ?? '').trim();
  } else if (!f.headerType && f.header?.trim()) {
    payload.header = f.header.trim(); // legacy: plain header text
  }
  if (f.footer?.trim()) payload.footer = f.footer.trim();
  if (count > 0) payload.sample_values = f.samples.slice(0, count).map((s) => s.trim()).join(',');
  if (f.buttons?.length) {
    payload.buttons = f.buttons.map((b) => {
      const out: TemplateButton = { type: b.type, text: b.text.trim() };
      if (b.type === 'URL') {
        out.url = (b.url ?? '').trim();
        if (out.url.includes('{{') && b.example?.trim()) out.example = b.example.trim();
      }
      if (b.type === 'PHONE_NUMBER') out.phone_number = (b.phone_number ?? '').trim();
      return out;
    });
  }
  return payload;
}

/**
 * Payload for editing an existing template: name and language are left out, and
 * cleared optional parts are sent empty so the server drops them.
 */
export function buildEditPayload(f: TemplateForm & { category: TemplateCategory }): EditTemplatePayload {
  const base = buildTemplatePayload(f);
  const rest: Partial<TemplatePayload> = { ...base };
  delete rest.template_name;
  delete rest.language_code;
  const out = { ...rest, header_type: rest.header_type ?? '', footer: rest.footer ?? '', buttons: rest.buttons ?? [] } as EditTemplatePayload;
  if (f.keepExistingMedia && (f.headerType === 'IMAGE' || f.headerType === 'DOCUMENT') && !f.headerSample?.trim()) {
    delete out.header_type;
    delete out.sample;
  }
  if (!rest.sample_values) out.sample_values = '';
  return out;
}

/** Validate an outbound media send before calling the server. */
export function validateMediaSend(f: { kind: MediaKind; link?: string; fileUrl?: string; caption?: string }): string | null {
  if (!f.link?.trim() && !f.fileUrl) return 'Add a file or paste a public link';
  if (f.link?.trim() && !/^https:\/\//.test(f.link.trim())) return 'The link must start with https://';
  if (f.kind === 'audio' && f.caption?.trim()) return 'Audio messages cannot have a caption';
  if ((f.caption ?? '').length > 1024) return 'Caption is limited to 1024 characters';
  return null;
}

export const getSetupStatus = (gatewayName?: string) =>
  invoke<SetupStatus>('get_setup_status', gatewayName ? { gateway_name: gatewayName } : {}, 'get');

// Every list/send/manage call names the Gateway it acts for: the server derives the WhatsApp
// account from that Gateway and never lists or sends across accounts.
export const listTemplates = (gatewayName: string, status?: string) =>
  invoke<{ templates: WhatsAppTemplate[]; manager_url?: string; business_id?: string }>(
    'list_templates',
    { gateway_name: gatewayName, status },
    'get',
  );

export const getTemplate = (name: string) => invoke<TemplateDetail>('get_template', { name }, 'get');

export const editTemplate = (name: string, payload: EditTemplatePayload) =>
  invoke<{ name: string; status?: string; edits_left?: number | null }>(
    'edit_template',
    { name, payload: JSON.stringify(payload) },
    'post',
  );

export const listTemplateDrafts = (gatewayName: string, status?: string) =>
  invoke<{ drafts: TemplateDraft[] }>('list_template_drafts', { gateway_name: gatewayName, status }, 'get');

export const createTemplateDraft = (gatewayName: string, payload: TemplatePayload) =>
  invoke<{ name: string; status: string; draft: TemplateDraft }>(
    'create_template_draft',
    { gateway_name: gatewayName, payload: JSON.stringify(payload) },
    'post',
  );

export const approveTemplateDraft = (name: string, note?: string) =>
  invoke<{ name: string; status: string; submitted_template?: string; submit_error?: string }>(
    'approve_template_draft',
    { name, note },
    'post',
  );

export const rejectTemplateDraft = (name: string, note?: string) =>
  invoke<{ name: string; status: string }>('reject_template_draft', { name, note }, 'post');

export const createTemplate = (gatewayName: string, payload: TemplatePayload) =>
  invoke<{ name: string; status?: string; id?: string }>(
    'create_template',
    { gateway_name: gatewayName, payload: JSON.stringify(payload) },
    'post',
  );

export const deleteTemplate = (name: string) => invoke<Record<string, unknown>>('delete_template', { name }, 'post');

export const syncTemplates = (gatewayName: string) =>
  invoke<Record<string, unknown>>('sync_templates', { gateway_name: gatewayName }, 'post');

export const sendTemplateMessage = (args: {
  /** The Gateway to send from; its WhatsApp account is used, never one chosen by the caller. */
  gateway_name: string;
  to: string;
  template_name: string;
  body_params?: string[];
  header_params?: HeaderParam[];
  button_params?: ButtonParam[];
}) =>
  invoke<Record<string, unknown>>(
    'send_template_message',
    {
      gateway_name: args.gateway_name,
      to: args.to,
      template_name: args.template_name,
      body_params: JSON.stringify(args.body_params ?? []),
      header_params: JSON.stringify(args.header_params ?? []),
      button_params: JSON.stringify(args.button_params ?? []),
    },
    'post',
  );

export const sendTextMessage = (gatewayName: string, to: string, text: string) =>
  invoke<Record<string, unknown>>('send_text_message', { gateway_name: gatewayName, to, text }, 'post');

export const sendMediaMessage = (
  gatewayName: string,
  to: string,
  media: { kind: MediaKind; link?: string; fileUrl?: string; caption?: string; filename?: string },
) =>
  invoke<Record<string, unknown>>(
    'send_media_message',
    {
      gateway_name: gatewayName,
      to,
      kind: media.kind,
      link: media.link?.trim() || undefined,
      file_url: media.fileUrl || undefined,
      caption: media.caption?.trim() || undefined,
      filename: media.filename?.trim() || undefined,
    },
    'post',
  );

/** Upload a public file (so Meta can fetch it) and return its server path. */
export async function uploadPublicFile(f: File): Promise<{ fileUrl: string } | WhatsAppError> {
  try {
    const res = await file.uploadFile(f, { isPrivate: false });
    const data = (res as { data?: { message?: { file_url?: string }; file_url?: string } }).data;
    const fileUrl = data?.message?.file_url || data?.file_url;
    if (!fileUrl) return { success: false, error: 'upload_failed', message: 'The upload did not return a file.' };
    return { fileUrl };
  } catch (err) {
    return { success: false, error: 'upload_failed', message: getFrappeErrorMessage(err) };
  }
}

export type MessageDirection = 'in' | 'out';
export type MessageSentBy = 'agent' | 'template' | 'manual' | 'customer';

export interface MessageLogItem {
  name: string;
  message_id: string | null;
  direction: MessageDirection;
  phone: string;
  profile_name: string | null;
  content_type: string | null;
  text: string | null;
  status: string | null;
  error: string | null;
  template: string | null;
  creation: string;
  gateway: string;
  agent: string | null;
  agent_run: string | null;
  event: string | null;
  sent_by: MessageSentBy | null;
}

export interface MessageLogQuery {
  direction?: MessageDirection;
  status?: string;
  agent?: string;
  template?: string;
  phone?: string;
  q?: string;
  date_from?: string;
  date_to?: string;
  cursor?: string;
  limit?: number;
}

export interface MessageLogFilterOptions {
  agents: { name: string; title: string }[];
  templates: string[];
  statuses: string[];
  directions: string[];
}

export const listMessageLog = (gatewayName: string, query: MessageLogQuery = {}) =>
  invoke<{ items: MessageLogItem[]; next_cursor: string | null; has_more: boolean }>(
    'list_message_log',
    { gateway_name: gatewayName, limit: 50, ...query },
    'get',
  );

export const listMessageLogFilters = (gatewayName: string) =>
  invoke<MessageLogFilterOptions>('list_message_log_filters', { gateway_name: gatewayName }, 'get');
