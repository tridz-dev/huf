import {
  extractPlaceholders,
  type HeaderType,
  type TemplateButton,
  type WhatsAppTemplate,
} from '@/services/whatsappApi';

export type BadgeTone = 'success' | 'warning' | 'danger' | 'neutral';

export interface StatusInfo {
  label: string;
  tone: BadgeTone;
  hint: string;
}

const STATUS_INFO: Record<string, StatusInfo> = {
  APPROVED: { label: 'Approved', tone: 'success', hint: 'Ready to send.' },
  PENDING: { label: 'In review', tone: 'warning', hint: 'WhatsApp is reviewing this template. This usually takes a few minutes.' },
  REJECTED: { label: 'Rejected', tone: 'danger', hint: 'WhatsApp did not approve this template. Edit it and resubmit.' },
  PAUSED: { label: 'Paused', tone: 'warning', hint: 'Sending is paused because customers reported low quality. Edit the template to improve it.' },
  DISABLED: { label: 'Disabled', tone: 'danger', hint: 'WhatsApp disabled this template after repeated low quality.' },
  IN_APPEAL: { label: 'In appeal', tone: 'warning', hint: 'An appeal is being reviewed by WhatsApp.' },
  LIMIT_EXCEEDED: { label: 'Limit exceeded', tone: 'danger', hint: 'The account hit its template limit, so this template cannot be used right now.' },
};

export const TEMPLATE_STATUSES = Object.keys(STATUS_INFO);

export function statusInfo(status?: string): StatusInfo {
  const key = (status || '').toUpperCase().replace(/\s+/g, '_');
  return STATUS_INFO[key] ?? { label: status ? titleCase(status) : 'Unknown', tone: 'neutral', hint: '' };
}

export function titleCase(value: string): string {
  const text = value.replace(/_/g, ' ').toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function qualityInfo(score?: string): { label: string; tone: BadgeTone } | null {
  switch ((score || '').toUpperCase()) {
    case 'GREEN': return { label: 'High quality', tone: 'success' };
    case 'YELLOW': return { label: 'Medium quality', tone: 'warning' };
    case 'RED': return { label: 'Low quality', tone: 'danger' };
    default: return null;
  }
}

const REJECTION_COPY: Record<string, { reason: string; advice: string }> = {
  ABUSIVE_CONTENT: {
    reason: 'The message contains language WhatsApp considers abusive or threatening.',
    advice: 'Remove offensive, threatening or harassing wording and keep the tone neutral.',
  },
  INCORRECT_CATEGORY: {
    reason: 'The category does not match what the message says.',
    advice: 'Switch the category (for example, promotional wording belongs in Marketing) and resubmit.',
  },
  INVALID_FORMAT: {
    reason: 'The template does not follow WhatsApp formatting rules.',
    advice: 'Check variables are numbered in order, are not at the start or end of the message, and have sample values.',
  },
  PROMOTIONAL: {
    reason: 'The message reads like a promotion but is not in the Marketing category.',
    advice: 'Move it to Marketing, or remove the promotional wording to keep it as Utility.',
  },
  SCAM: {
    reason: 'WhatsApp flagged the message as possibly misleading or a scam.',
    advice: 'Remove urgent or too-good-to-be-true wording, and make sure links point to your own website.',
  },
  TAG_CONTENT_MISMATCH: {
    reason: 'The content does not match the selected category.',
    advice: 'Make the wording fit the category you picked, or change the category, then resubmit.',
  },
};

/** Friendly explanation for a Meta rejection reason; unknown values still get a sentence. */
export function rejectionCopy(reason?: string): { reason: string; advice: string } | null {
  const key = (reason || '').toUpperCase();
  if (!key || key === 'NONE') return null;
  return (
    REJECTION_COPY[key] ?? {
      reason: 'WhatsApp did not approve this template.',
      advice: 'Review the wording against the WhatsApp template guidelines, then edit and resubmit.',
    }
  );
}

/** Replace {{n}} with the n-th sample; blank samples keep the placeholder visible. */
export function fillVariables(text: string, samples: readonly string[]): string {
  return text.replace(/\{\{\s*(\d+)\s*\}\}/g, (match, n: string) => {
    const value = samples[Number(n) - 1];
    return value && value.trim() ? value : match;
  });
}

/** Next unused variable number for a body ("Hi {{1}}" -> 2). */
export function nextVariableNumber(body: string): number {
  const found = extractPlaceholders(body);
  return found.length ? Math.max(...found) + 1 : 1;
}

/** Insert `{{n}}` at the caret (or the end) and return the new text and caret. */
export function insertVariable(body: string, caret: number | null): { body: string; caret: number; number: number } {
  const at = caret === null || caret < 0 || caret > body.length ? body.length : caret;
  const number = nextVariableNumber(body);
  const token = `{{${number}}}`;
  return { body: body.slice(0, at) + token + body.slice(at), caret: at + token.length, number };
}

export interface PreviewInput {
  headerType?: HeaderType | '';
  header?: string;
  headerSample?: string;
  body: string;
  samples: readonly string[];
  footer?: string;
  buttons?: readonly TemplateButton[];
}

export interface PreviewModel {
  header: { kind: 'text'; text: string } | { kind: 'media'; media: 'IMAGE' | 'DOCUMENT'; url: string } | null;
  body: string;
  footer: string;
  buttons: { type: TemplateButton['type']; text: string }[];
}

export function buildPreviewModel(input: PreviewInput): PreviewModel {
  let header: PreviewModel['header'] = null;
  if (input.headerType === 'TEXT' && input.header?.trim()) {
    header = { kind: 'text', text: fillVariables(input.header, [input.headerSample ?? '']) };
  } else if (input.headerType === 'IMAGE' || input.headerType === 'DOCUMENT') {
    header = { kind: 'media', media: input.headerType, url: (input.headerSample ?? '').trim() };
  }
  return {
    header,
    body: fillVariables(input.body, input.samples),
    footer: input.footer?.trim() ?? '',
    buttons: (input.buttons ?? []).map((b) => ({ type: b.type, text: b.text.trim() || 'Button' })),
  };
}

const LIST_BUTTON_TYPES: Record<string, TemplateButton['type']> = {
  'Quick Reply': 'QUICK_REPLY',
  'Visit Website': 'URL',
  'Call Phone': 'PHONE_NUMBER',
};

/** Preview input from a list row (buttons arrive in the stored format). */
export function rowToPreviewInput(row: WhatsAppTemplate, samples?: readonly string[]): PreviewInput {
  return {
    headerType: row.header_type ?? '',
    header: row.header,
    body: row.template ?? '',
    samples: samples ?? (row.sample_values ?? '').split(',').filter(Boolean),
    footer: row.footer,
    buttons: (row.buttons ?? []).map((b) => ({
      type: LIST_BUTTON_TYPES[b.button_type] ?? 'QUICK_REPLY',
      text: b.button_label ?? '',
    })),
  };
}

export interface TemplateFilters {
  search: string;
  status: string;
  category: string;
  language: string;
  /** Solution name to match against `used_by`; unset or ALL_OPTION = any. */
  solution?: string;
}

export const ALL_OPTION = '__all__';

export function filterTemplates(rows: readonly WhatsAppTemplate[], f: TemplateFilters): WhatsAppTemplate[] {
  const q = f.search.trim().toLowerCase();
  return rows.filter((t) => {
    if (f.status !== ALL_OPTION && (t.status || '').toUpperCase() !== f.status) return false;
    if (f.category !== ALL_OPTION && (t.category || '').toUpperCase() !== f.category) return false;
    if (f.language !== ALL_OPTION && t.language_code !== f.language) return false;
    if (f.solution && f.solution !== ALL_OPTION && !(t.used_by ?? []).some((u) => u.solution === f.solution)) return false;
    if (!q) return true;
    return `${t.template_name || t.name} ${t.template ?? ''}`.toLowerCase().includes(q);
  });
}

/** Server timestamps are naive strings ("2026-10-14 10:00:00.123456") or ISO. */
export function parseServerTime(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value.includes('T') ? value : value.replace(' ', 'T'));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function timeAgo(value?: string | null, now: Date = new Date()): string {
  const date = parseServerTime(value);
  if (!date) return '';
  const seconds = Math.max(0, Math.round((now.getTime() - date.getTime()) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} d ago`;
}

export const OPEN_DRAFT_STATUSES = ['Draft', 'Pending Review', 'Failed'];

export function draftStatusInfo(status?: string): { label: string; tone: BadgeTone } {
  switch (status) {
    case 'Pending Review': return { label: 'Awaiting approval', tone: 'warning' };
    case 'Draft': return { label: 'Draft', tone: 'neutral' };
    case 'Failed': return { label: 'Could not submit', tone: 'danger' };
    case 'Approved & Submitted': return { label: 'Submitted', tone: 'success' };
    case 'Rejected': return { label: 'Rejected', tone: 'danger' };
    default: return { label: status || 'Unknown', tone: 'neutral' };
  }
}

/** Short sentence for the realtime status toast. */
export function statusToastText(template: string, status?: string): { text: string; tone: 'success' | 'error' | 'info' } {
  switch ((status || '').toUpperCase()) {
    case 'APPROVED': return { text: `Template ${template} approved`, tone: 'success' };
    case 'REJECTED': return { text: `Template ${template} rejected`, tone: 'error' };
    case 'PAUSED': return { text: `Template ${template} paused`, tone: 'error' };
    case 'DISABLED': return { text: `Template ${template} disabled`, tone: 'error' };
    default: return { text: `Template ${template} is now ${statusInfo(status).label.toLowerCase()}`, tone: 'info' };
  }
}

/** "MARKETING" -> "Marketing"; any category WhatsApp adds later reads the same way. */
export function categoryLabel(category?: string | null): string {
  const c = (category || '').trim();
  return c ? c.charAt(0).toUpperCase() + c.slice(1).toLowerCase() : '';
}

/** Shared when the server says so, or when more than one solution uses it. */
export function isSharedTemplate(t: Pick<WhatsAppTemplate, 'shared' | 'used_by'>): boolean {
  return t.shared ?? (t.used_by?.length ?? 0) > 1;
}

/** "Orders and Customer care" / "A, B and C". */
export function joinTitles(users: readonly { title: string; solution: string }[]): string {
  const names = users.map((u) => u.title || u.solution);
  if (names.length <= 1) return names[0] ?? '';
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}
