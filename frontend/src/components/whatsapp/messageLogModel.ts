import type { MessageDirection, MessageLogItem, MessageLogQuery, MessageSentBy } from '@/services/whatsappApi';

export const ALL = 'all';

export interface MessageLogFilters {
  q: string;
  direction: '' | MessageDirection;
  status: string;
  agent: string;
  template: string;
  solution: string;
  phone: string;
  from: string;
  to: string;
}

export const EMPTY_FILTERS: MessageLogFilters = { q: '', direction: '', status: '', agent: '', template: '', solution: '', phone: '', from: '', to: '' };

const FILTER_KEYS = Object.keys(EMPTY_FILTERS) as (keyof MessageLogFilters)[];

export function filtersFromParams(params: URLSearchParams): MessageLogFilters {
  const direction = params.get('direction');
  return {
    ...EMPTY_FILTERS,
    ...Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ''])),
    direction: direction === 'in' || direction === 'out' ? direction : '',
  };
}

/** Writes the filters into a copy of `base`, leaving unrelated params (gateway, tab) untouched. */
export function filtersToParams(filters: MessageLogFilters, base: URLSearchParams = new URLSearchParams()): URLSearchParams {
  const next = new URLSearchParams(base);
  for (const k of FILTER_KEYS) {
    const value = filters[k].trim();
    if (value) next.set(k, value);
    else next.delete(k);
  }
  return next;
}

export function activeFilterCount(filters: MessageLogFilters): number {
  return FILTER_KEYS.filter((k) => filters[k].trim() !== '').length;
}

export function filtersToQuery(filters: MessageLogFilters): MessageLogQuery {
  const query: MessageLogQuery = {};
  if (filters.direction) query.direction = filters.direction;
  if (filters.status) query.status = filters.status;
  if (filters.agent) query.agent = filters.agent;
  if (filters.template) query.template = filters.template;
  if (filters.solution) query.solution = filters.solution;
  if (filters.phone.trim()) query.phone = filters.phone.trim();
  if (filters.q.trim()) query.q = filters.q.trim();
  if (filters.from) query.date_from = filters.from;
  if (filters.to) query.date_to = filters.to;
  return query;
}

export type TickTone = 'neutral' | 'good' | 'danger';
export interface StatusTicks {
  label: string;
  /** 0 = not yet accepted, 1 = sent, 2 = delivered or read. */
  ticks: 0 | 1 | 2;
  tone: TickTone;
}

export function statusTicks(status?: string | null): StatusTicks {
  switch ((status ?? '').toLowerCase()) {
    case 'sent': return { label: 'Sent', ticks: 1, tone: 'neutral' };
    case 'delivered': return { label: 'Delivered', ticks: 2, tone: 'neutral' };
    case 'read': return { label: 'Read', ticks: 2, tone: 'good' };
    case 'played': return { label: 'Played', ticks: 2, tone: 'good' };
    case 'failed': return { label: 'Failed', ticks: 0, tone: 'danger' };
    case 'received': return { label: 'Received', ticks: 0, tone: 'neutral' };
    case '': return { label: 'Unknown', ticks: 0, tone: 'neutral' };
    default: {
      const s = status!.toLowerCase();
      return { label: s[0].toUpperCase() + s.slice(1), ticks: 0, tone: 'neutral' };
    }
  }
}

/** Incoming messages are not "Succeeded": unless they failed, they were simply received. */
export function displayStatus(item: Pick<MessageLogItem, 'direction' | 'status'>): string | null | undefined {
  if (item.direction === 'in' && (item.status ?? '').toLowerCase() !== 'failed') return 'received';
  return item.status;
}

export function sentByLabel(sentBy?: MessageSentBy | null, agentTitle?: string | null): string {
  if (agentTitle) return agentTitle;
  switch (sentBy) {
    case 'agent': return 'Agent';
    case 'template': return 'Template send';
    case 'manual': return 'Manual';
    case 'customer': return 'Customer';
    default: return 'Unknown';
  }
}

export function agentRunPath(item: Pick<MessageLogItem, 'agent_run'>): string | null {
  return item.agent_run ? `/executions/${encodeURIComponent(item.agent_run)}` : null;
}

export function messagePreview(item: Pick<MessageLogItem, 'text' | 'content_type' | 'template'>, max = 90): string {
  const text = (item.text ?? '').replace(/\s+/g, ' ').trim();
  if (!text) return item.template ? `Template: ${item.template}` : `[${item.content_type || 'message'}]`;
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export interface TimelineStep {
  key: 'sent' | 'delivered' | 'read' | 'played' | 'failed';
  label: string;
  reached: boolean;
}

/** Steps the status timeline shows for an outgoing message; a failure replaces the later steps. */
export function statusTimeline(status?: string | null): TimelineStep[] {
  const s = (status ?? '').toLowerCase();
  if (s === 'failed') return [{ key: 'sent', label: 'Sent', reached: true }, { key: 'failed', label: 'Failed', reached: true }];
  const rank = { sent: 1, delivered: 2, read: 3, played: 3 }[s as 'sent' | 'delivered' | 'read' | 'played'] ?? 0;
  return [
    { key: 'sent', label: 'Sent', reached: rank >= 1 },
    { key: 'delivered', label: 'Delivered', reached: rank >= 2 },
    s === 'played' ? { key: 'played', label: 'Played', reached: true } : { key: 'read', label: 'Read', reached: rank >= 3 },
  ];
}

export interface ErrorInfo {
  /** Meta error code when the message carries one, for example 131047. */
  code: number | null;
  label: string;
  hint: string;
}

const KNOWN_ERRORS: Record<number, { label: string; hint: string }> = {
  131047: { label: 'Window closed', hint: 'The 24-hour reply window has ended. Send an approved template instead.' },
  131026: { label: 'Not deliverable', hint: 'The number is not on WhatsApp or has not accepted the latest terms.' },
  131049: { label: 'Held back by Meta', hint: 'Meta limited this marketing message to protect the recipient. Try again later.' },
  131030: { label: 'Number not allowed', hint: 'This number is not on the allowed recipient list for the account.' },
  131051: { label: 'Unsupported file', hint: 'The message type or file format is not supported.' },
  131053: { label: 'Media problem', hint: 'The file could not be downloaded or is too large.' },
  132000: { label: 'Template values', hint: 'The number of template values does not match the template.' },
  132001: { label: 'Template missing', hint: 'The template does not exist in that language or is not approved.' },
  132012: { label: 'Template values', hint: 'A template value does not match the expected format.' },
  130429: { label: 'Rate limited', hint: 'Too many messages were sent at once. Slow down and retry.' },
  131056: { label: 'Rate limited', hint: 'Too many messages to this number. Wait and retry.' },
  133010: { label: 'Number not registered', hint: 'The sending number is not registered with WhatsApp.' },
  190: { label: 'Token expired', hint: 'The access token is no longer valid. Add a new token in Settings.' },
  100: { label: 'Invalid request', hint: 'Meta rejected part of the request. Check the message content.' },
  10: { label: 'Permission missing', hint: 'The token does not have permission for this action.' },
};

const KIND_PATTERNS: [RegExp, { label: string; hint: string }][] = [
  [/window|24[- ]hour|outside the allowed/i, { label: 'Window closed', hint: 'The 24-hour reply window has ended. Send an approved template instead.' }],
  [/rate.?limit|too many|throttl/i, { label: 'Rate limited', hint: 'Too many messages were sent at once. Slow down and retry.' }],
  [/token|auth|oauth|expired/i, { label: 'Sign-in problem', hint: 'The access token may be invalid or expired. Check it in Settings.' }],
  [/template/i, { label: 'Template problem', hint: 'Check that the template exists, is approved and has the right values.' }],
  [/media|file|image|video|audio/i, { label: 'Media problem', hint: 'Check the file type, size and that the link is public.' }],
  [/recipient|phone|number/i, { label: 'Recipient problem', hint: 'Check that the number is correct and on WhatsApp.' }],
  [/timeout|timed out|5\d\d|server/i, { label: 'Temporary problem', hint: 'Meta did not respond in time. Try again shortly.' }],
];

/** Plain-language badge and hint for a delivery error string; null when there is no error. */
export function errorInfo(error?: string | null): ErrorInfo | null {
  const text = (error ?? '').trim();
  if (!text) return null;
  const m = text.match(/(?:#|\bcode[:\s]+|\()(\d{2,6})\b/i) ?? text.match(/\b(1[3][0-3]\d{3})\b/);
  const code = m ? Number(m[1]) : null;
  const known = code !== null ? KNOWN_ERRORS[code] : undefined;
  if (known) return { code, ...known };
  const byText = KIND_PATTERNS.find(([re]) => re.test(text));
  if (byText) return { code, ...byText[1] };
  return { code, label: code ? `Error ${code}` : 'Delivery error', hint: 'See the full message for details.' };
}
