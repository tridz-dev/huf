import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

const BASE = 'huf.ai.channels.api';

export type ConversationStatus = 'ai' | 'handed_off' | 'closed';

export interface ChannelConversation {
  name: string;
  gateway: string;
  channel?: string | null;
  contact_handle: string | null;
  contact_name: string | null;
  status: ConversationStatus;
  agent?: string | null;
  last_inbound_at?: string | null;
  last_outbound_at?: string | null;
  last_message_preview: string | null;
  message_count?: number;
  modified: string;
  within_24h: boolean;
}

export interface ConversationMessage {
  direction: 'in' | 'out';
  event: string;
  message_id: string | null;
  text: string;
  status: string;
  error: string | null;
  creation: string;
  agent: string | null;
  agent_run: string | null;
  sent_by: string;
}

export interface ConversationDetail extends ChannelConversation {
  messages: ConversationMessage[];
  tool_calls?: unknown[];
}

export interface ConversationList {
  items: ChannelConversation[];
  has_more: boolean;
}

export type ChannelsResult<T> = { ok: true; data: T } | { ok: false; error: string };

async function get<T>(method: string, args: Record<string, unknown>): Promise<ChannelsResult<T>> {
  try {
    const res = await call.get(`${BASE}.${method}`, args);
    const body = ((res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res) ?? {}) as T & {
      success?: boolean;
      error?: string;
    };
    if (body.success === false) return { ok: false, error: body.error || 'Request failed' };
    return { ok: true, data: body };
  } catch (e) {
    return { ok: false, error: getFrappeErrorMessage(e) };
  }
}

export function listConversations(
  gateway: string,
  opts: { status?: ConversationStatus; search?: string; limit?: number; start?: number } = {},
) {
  const args: Record<string, unknown> = { gateway };
  if (opts.status) args.status = opts.status;
  if (opts.search) args.search = opts.search;
  if (opts.limit) args.limit = opts.limit;
  if (opts.start) args.start = opts.start;
  return get<ConversationList>('list_conversations', args);
}

export function getConversation(name: string) {
  return get<{ conversation?: ConversationDetail } & Partial<ConversationDetail>>('get_conversation', { name });
}
