import { call, file } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

const BASE = 'huf.ai.whatsapp.management';

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
  /** Structured Meta (Graph) error detail; `message` is already the best human text. */
  user_title?: string;
  user_msg?: string;
  /** Numeric Graph error code (the string `error` is Huf's own code). */
  graph_code?: number | null;
  subcode?: number | null;
  kind?: string;
  retryable?: boolean;
  operator_text?: string;
  trace_id?: string;
  /** Edit refused: the quota was not used. */
  quota_used?: boolean;
  edit_blocked_until?: string | null;
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
  /** Solutions using this template (absent on servers without Solutions). */
  used_by?: TemplateUser[];
  shared?: boolean;
  owner?: TemplateUser | null;
}

export interface TemplateUser {
  solution: string;
  title: string;
}

export interface NamedSample {
  name: string;
  example: string;
}

export interface TemplateDetail {
  name: string;
  template_id: string;
  template_name: string;
  language_code: string;
  category: string;
  correct_category: string;
  category_change_pending: boolean;
  /** Category Meta had before it reclassified the template, when it did. */
  previous_category?: string;
  category_changed_by_meta?: boolean;
  status: string;
  whatsapp_account?: string;
  components: {
    header: { type: WizardPayloadHeaderType; text: string; sample: string } | null;
    body: { text: string; sample_values: string[]; named_samples?: NamedSample[] };
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
  /** Present once the server reports variable style and validity (wizard edit mode). */
  parameter_format?: 'POSITIONAL' | 'NAMED';
  ttl_seconds?: number | null;
  /** Header format as WhatsApp stores it, e.g. TEXT, IMAGE, VIDEO, LOCATION. */
  header_format?: string;
  /** Named-variable examples ({name, example}); empty for numbered variables. */
  named_samples?: NamedSample[];
  editable: boolean;
  editable_reason?: string;
  editable_message?: string;
  edits_left?: number | null;
  next_edit_at?: string | null;
  edit_blocked_until?: string | null;
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
  payload: Partial<WizardTemplatePayload>;
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

/** Wizard payload (three-step flow). Extends the flat payload with named variables, video/location headers, copy-code buttons and TTL. */
export type WizardPayloadHeaderType = HeaderType | 'VIDEO' | 'LOCATION';
export interface WizardPayloadButton {
  type: TemplateButtonType | 'COPY_CODE';
  text: string;
  url?: string;
  /** URL buttons: example full link. COPY_CODE: example code. */
  example?: string;
  phone_number?: string;
}
export interface WizardTemplatePayload {
  template_name: string;
  category: TemplateCategory;
  language_code: string;
  template: string;
  parameter_format: 'POSITIONAL' | 'NAMED';
  /** POSITIONAL: body samples in order, comma-joined. */
  sample_values?: string;
  /** NAMED: body sample per variable name. */
  named_samples?: Record<string, string>;
  header_type?: WizardPayloadHeaderType;
  header?: string;
  /** Text header variable example, or media sample (link / uploaded path). */
  sample?: string;
  footer?: string;
  buttons?: WizardPayloadButton[];
  /** Utility only: message validity in seconds. */
  ttl_seconds?: number;
}
export type WizardEditPayload = Omit<WizardTemplatePayload, 'template_name' | 'language_code' | 'header_type'> & {
  header_type?: WizardPayloadHeaderType | '';
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
    edit_blocked: "Meta won't let this template be edited right now. Try again later or create a new version.",
    media_link_unreachable: "WhatsApp can't download this link. Upload the file instead.",
    media_link_wrong_type: 'This link is a web page or the wrong kind of file. Upload the file instead.',
    media_link_too_large: 'The file at this link is larger than WhatsApp allows. Upload a smaller file.',
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

const VOICE_EXT = /\.(ogg|opus|oga)$/i;

/** A WhatsApp voice note must be an Ogg/Opus file; checks the link or uploaded file name before calling the server. */
export function validateVoiceNote(f: { link?: string; fileUrl?: string; fileName?: string }): string | null {
  const link = f.link?.trim();
  if (!link && !f.fileUrl) return 'Add a file or paste a public link';
  if (link && !/^https:\/\//.test(link)) return 'The link must start with https://';
  const target = (link ? link.split(/[?#]/)[0] : f.fileName || f.fileUrl || '').trim();
  return VOICE_EXT.test(target) ? null : 'A voice note must be an Ogg file with the Opus codec (.ogg or .opus)';
}

export const getSetupStatus = (gatewayName?: string) =>
  invoke<SetupStatus>('get_setup_status', gatewayName ? { gateway_name: gatewayName } : {}, 'get');

// Every list/send/manage call names the Gateway it acts for: the server derives the WhatsApp
// account from that Gateway and never lists or sends across accounts.
export const listTemplates = (gatewayName: string, status?: string, solution?: string) =>
  invoke<{ templates: WhatsAppTemplate[]; manager_url?: string; business_id?: string }>(
    'list_templates',
    { gateway_name: gatewayName, status, ...(solution ? { solution } : {}) },
    'get',
  );

export const getTemplate = (name: string) => invoke<TemplateDetail>('get_template', { name }, 'get');

export const editTemplate = (name: string, payload: EditTemplatePayload | WizardEditPayload, acknowledgeShared?: boolean) =>
  throwIfShared(
    invoke<{ name: string; status?: string; edits_left?: number | null }>(
      'edit_template',
      {
        name,
        payload: JSON.stringify(payload),
        ...(acknowledgeShared ? { acknowledge_shared: true } : {}),
      },
      'post',
    ),
  );

export const listTemplateDrafts = (gatewayName: string, status?: string) =>
  invoke<{ drafts: TemplateDraft[] }>('list_template_drafts', { gateway_name: gatewayName, status }, 'get');

export const createTemplateDraft = (gatewayName: string, payload: TemplatePayload | WizardTemplatePayload) =>
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

export const createTemplate = (gatewayName: string, payload: TemplatePayload | WizardTemplatePayload) =>
  invoke<{ name: string; status?: string; id?: string }>(
    'create_template',
    { gateway_name: gatewayName, payload: JSON.stringify(payload) },
    'post',
  );

export const deleteTemplate = (name: string, acknowledgeShared?: boolean) =>
  throwIfShared(
    invoke<Record<string, unknown>>('delete_template', { name, ...(acknowledgeShared ? { acknowledge_shared: true } : {}) }, 'post'),
  );

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

/** Send audio as a voice note (`audio.voice: true`); Ogg/Opus only. */
export const sendVoiceNote = (gatewayName: string, to: string, voice: { link?: string; fileUrl?: string }) =>
  invoke<Record<string, unknown>>(
    'send_voice_note',
    { gateway_name: gatewayName, to, link: voice.link?.trim() || undefined, file_url: voice.fileUrl || undefined },
    'post',
  );

export interface StickerSend { link?: string; fileUrl?: string }
export const sendStickerMessage = (gatewayName: string, to: string, sticker: StickerSend) =>
  invoke<Record<string, unknown>>(
    'send_sticker_message',
    { gateway_name: gatewayName, to, link: sticker.link?.trim() || undefined, file_url: sticker.fileUrl || undefined },
    'post',
  );

export interface LocationSend { latitude: number; longitude: number; name?: string; address?: string }
export const sendLocationMessage = (gatewayName: string, to: string, loc: LocationSend) =>
  invoke<Record<string, unknown>>(
    'send_location_message',
    {
      gateway_name: gatewayName,
      to,
      latitude: loc.latitude,
      longitude: loc.longitude,
      name: loc.name?.trim() || undefined,
      address: loc.address?.trim() || undefined,
    },
    'post',
  );

export interface ContactCard {
  name: { formatted_name: string };
  phones?: { phone: string }[];
  emails?: { email: string }[];
  org?: { company: string };
}
export const sendContactsMessage = (gatewayName: string, to: string, contacts: ContactCard[]) =>
  invoke<Record<string, unknown>>(
    'send_contacts_message',
    { gateway_name: gatewayName, to, contacts: JSON.stringify(contacts) },
    'post',
  );

export const sendReactionMessage = (gatewayName: string, to: string, messageId: string, emoji: string, remove = false) =>
  invoke<Record<string, unknown>>(
    'send_reaction_message',
    { gateway_name: gatewayName, to, message_id: messageId.trim(), emoji: remove ? '' : emoji.trim(), remove: remove ? 1 : 0 },
    'post',
  );

export type InteractiveKind = 'buttons' | 'list' | 'cta_url';
export interface InteractiveButton { id: string; title: string }
export interface InteractiveSection { title: string; rows: { id: string; title: string; description?: string }[] }
export interface InteractiveSend {
  kind: InteractiveKind;
  body: string;
  header?: string;
  footer?: string;
  buttons?: InteractiveButton[];
  buttonText?: string;
  sections?: InteractiveSection[];
  displayText?: string;
  url?: string;
}
export const INTERACTIVE_LIMITS = { buttons: 3, buttonTitle: 20, listRows: 10, rowTitle: 24, ctaText: 20 } as const;

/** Validate an interactive message before calling the server. */
export function validateInteractive(m: InteractiveSend): string | null {
  if (!m.body.trim()) return 'Add the message text';
  if (m.kind === 'buttons') {
    const b = m.buttons ?? [];
    if (b.length < 1) return 'Add at least one button';
    if (b.length > INTERACTIVE_LIMITS.buttons) return 'Use at most 3 buttons';
    if (b.some((x) => !x.title.trim())) return 'Every button needs a label';
    if (b.some((x) => x.title.length > INTERACTIVE_LIMITS.buttonTitle)) return 'Button labels are limited to 20 characters';
  } else if (m.kind === 'list') {
    const rows = (m.sections ?? []).flatMap((s) => s.rows);
    if (!m.buttonText?.trim()) return 'Add the label for the list button';
    if (rows.length < 1) return 'Add at least one list item';
    if (rows.length > INTERACTIVE_LIMITS.listRows) return 'A list can have at most 10 items';
    if (rows.some((r) => !r.title.trim() || r.title.length > INTERACTIVE_LIMITS.rowTitle)) return 'List item titles are required and limited to 24 characters';
  } else {
    if (!m.displayText?.trim()) return 'Add the button label';
    if (!/^https:\/\//.test((m.url ?? '').trim())) return 'The link must start with https://';
  }
  return null;
}

export const sendInteractiveMessage = (gatewayName: string, to: string, m: InteractiveSend) =>
  invoke<Record<string, unknown>>(
    'send_interactive_message',
    {
      gateway_name: gatewayName,
      to,
      kind: m.kind,
      body: m.body.trim(),
      header: m.header?.trim() || undefined,
      footer: m.footer?.trim() || undefined,
      buttons: m.kind === 'buttons' ? JSON.stringify(m.buttons ?? []) : undefined,
      button_text: m.kind === 'list' ? m.buttonText?.trim() : undefined,
      sections: m.kind === 'list' ? JSON.stringify(m.sections ?? []) : undefined,
      display_text: m.kind === 'cta_url' ? m.displayText?.trim() : undefined,
      url: m.kind === 'cta_url' ? m.url?.trim() : undefined,
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

/** Thrown by editTemplate/deleteTemplate when other solutions use the template and the change was not acknowledged. */
export class SharedTemplateError extends Error {
  readonly code = 'shared_template';
  constructor(public readonly usedBy: TemplateUser[], message?: string) {
    super(message || 'This template is shared.');
    this.name = 'SharedTemplateError';
  }
}

async function throwIfShared<T>(pending: Promise<WhatsAppResult<T>>): Promise<WhatsAppResult<T>> {
  const res = await pending;
  if (!res.success && res.error === 'shared_template') {
    throw new SharedTemplateError((res as { used_by?: TemplateUser[] }).used_by ?? [], res.message);
  }
  return res;
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
  /** Absent when the server has no Solutions support. */
  solution?: { name: string; title: string } | null;
}

export interface MessageLogQuery {
  direction?: MessageDirection;
  status?: string;
  agent?: string;
  template?: string;
  solution?: string;
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
  solutions?: { name: string; title: string }[];
}

export const listMessageLog = (gatewayName: string, query: MessageLogQuery = {}) =>
  invoke<{ items: MessageLogItem[]; next_cursor: string | null; has_more: boolean }>(
    'list_message_log',
    { gateway_name: gatewayName, limit: 50, ...query },
    'get',
  );

export const listMessageLogFilters = (gatewayName: string) =>
  invoke<MessageLogFilterOptions>('list_message_log_filters', { gateway_name: gatewayName }, 'get');

// ---- Broadcast ------------------------------------------------------------

export type BroadcastStatus = 'Draft' | 'Queued' | 'Running' | 'Paused' | 'Completed' | 'Cancelled' | 'Failed';
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
  warnings: string[];
  blocking: string[];
  cost: BroadcastCost | null;
  confirm_required: boolean;
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
    warnings: Array.isArray(l.warnings) ? l.warnings : [],
    blocking: Array.isArray(l.blocking) ? l.blocking : [],
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
  invoke<{ broadcast: string; status: string; category?: string | null }>(
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
  header: Record<string, unknown> | null;
  buttons: unknown[];
}

export const getBroadcastTemplateParams = (gateway: string, template: string) =>
  mapOk(
    invoke<Partial<BroadcastTemplateParams>>('get_broadcast_template_params', { gateway, template }, 'get'),
    (r): BroadcastTemplateParams => ({
      parameter_format: r.parameter_format === 'NAMED' ? 'NAMED' : 'POSITIONAL',
      body: Array.isArray(r.body) ? r.body : [],
      header: r.header ?? null,
      buttons: Array.isArray(r.buttons) ? r.buttons : [],
    }),
  );

export const addBroadcastRecipients = (broadcast: string, opts: { recipients?: BroadcastRecipientInput[]; csvText?: string }) =>
  mapOk(
    invoke<AddRecipientsResult>(
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
  invoke<{ broadcast?: string; consent_attested?: boolean; consent_source?: string }>(
    'attest_broadcast_consent', { broadcast, consent_source: consentSource }, 'post');

export const previewBroadcast = (broadcast: string) =>
  mapOk(invoke<Record<string, any>>('preview_broadcast', { broadcast }, 'get'), (r) => ({ preview: adaptPreview(r) }));

export const startBroadcast = (broadcast: string, confirmCount: string | number) =>
  invoke<Mutated & { queued?: number }>('start_broadcast', { broadcast, confirm_count: String(confirmCount) }, 'post');

export const pauseBroadcast = (broadcast: string) => invoke<Mutated>('pause_broadcast', { broadcast }, 'post');
export const resumeBroadcast = (broadcast: string) => invoke<Mutated>('resume_broadcast', { broadcast }, 'post');
export const cancelBroadcast = (broadcast: string) => invoke<Mutated>('cancel_broadcast', { broadcast }, 'post');
export const pauseAllBroadcasts = (gateway: string) => invoke<{ gateway?: string; paused?: string[] }>('pause_all_broadcasts', { gateway }, 'post');

export const listBroadcasts = (opts: { gateway?: string; status?: string; limit?: number; offset?: number } = {}) =>
  mapOk(invoke<{ broadcasts: Record<string, unknown>[] }>('list_broadcasts', opts, 'get'),
    (r) => ({ broadcasts: (r.broadcasts ?? []).map(adaptBroadcast) }));

export const getBroadcast = (broadcast: string) =>
  mapOk(invoke<{ broadcast: Record<string, unknown> }>('get_broadcast', { broadcast }, 'get'),
    (r) => ({ broadcast: adaptBroadcast(r.broadcast) }));

export const listBroadcastRecipients = (broadcast: string, opts: { status?: string; limit?: number; offset?: number } = {}) =>
  invoke<{ recipients: BroadcastRecipient[] }>('list_broadcast_recipients', { broadcast, ...opts }, 'get');
