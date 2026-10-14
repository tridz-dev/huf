import type { MessageDirection, MessageLogItem, MessageLogQuery, MessageSentBy } from '@/services/whatsappApi';

export const ALL = 'all';

export interface MessageLogFilters {
  q: string;
  direction: '' | MessageDirection;
  status: string;
  agent: string;
  template: string;
  phone: string;
  from: string;
  to: string;
}

export const EMPTY_FILTERS: MessageLogFilters = { q: '', direction: '', status: '', agent: '', template: '', phone: '', from: '', to: '' };

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
    case 'failed': return { label: 'Failed', ticks: 0, tone: 'danger' };
    case 'received': return { label: 'Received', ticks: 0, tone: 'neutral' };
    case '': return { label: 'Unknown', ticks: 0, tone: 'neutral' };
    default: {
      const s = status!.toLowerCase();
      return { label: s[0].toUpperCase() + s.slice(1), ticks: 0, tone: 'neutral' };
    }
  }
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
  key: 'sent' | 'delivered' | 'read' | 'failed';
  label: string;
  reached: boolean;
}

/** Steps the status timeline shows for an outgoing message; a failure replaces the later steps. */
export function statusTimeline(status?: string | null): TimelineStep[] {
  const s = (status ?? '').toLowerCase();
  if (s === 'failed') return [{ key: 'sent', label: 'Sent', reached: true }, { key: 'failed', label: 'Failed', reached: true }];
  const rank = { sent: 1, delivered: 2, read: 3 }[s as 'sent' | 'delivered' | 'read'] ?? 0;
  return [
    { key: 'sent', label: 'Sent', reached: rank >= 1 },
    { key: 'delivered', label: 'Delivered', reached: rank >= 2 },
    { key: 'read', label: 'Read', reached: rank >= 3 },
  ];
}
