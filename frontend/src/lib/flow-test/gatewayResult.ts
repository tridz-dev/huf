/**
 * A chat trigger's test result for a person: friendly row names, and the bookkeeping fields (record names, ids,
 * the raw event kind) in a separate "Details" group so the main rows are only what the customer sent.
 */
const DETAIL_KEYS = ['gateway_event', 'wa_id', 'kind', 'message_id', 'thread_id', 'conversation_id', 'sender_id', 'provider', 'reply_to_message_id'];

export const GATEWAY_LABELS: Record<string, string> = {
  text: 'Message text',
  message: 'Message text',
  display_name: 'Sender name',
  gateway: 'Channel',
  message_type: 'Kind of message',
  attachments: 'Files',
  received_at: 'Received at',
  is_room: 'In a group',
  mentioned: 'Mentioned the bot',
  interactive_reply: 'Button chosen',
  button_title: 'Button chosen',
  command_args: 'Text after the command',
  gateway_event: 'Message record',
  wa_id: 'WhatsApp number',
  kind: 'Event type',
  message_id: 'Message number',
  thread_id: 'Thread',
  conversation_id: 'Conversation',
  sender_id: 'Sender',
  provider: 'Channel type',
  reply_to_message_id: 'Replying to',
};

export interface GatewayResultSplit {
  main: Record<string, unknown>;
  details: Record<string, unknown>;
}

/** True for the payload of a chat trigger (it always carries the message record or the channel with a sender). */
export function isGatewayOutput(output: unknown): output is Record<string, unknown> {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return false;
  const o = output as Record<string, unknown>;
  return 'gateway_event' in o || 'wa_id' in o || ('gateway' in o && 'sender_id' in o);
}

export function splitGatewayOutput(output: Record<string, unknown>): GatewayResultSplit {
  const main: Record<string, unknown> = {};
  const details: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(output)) (DETAIL_KEYS.includes(k) ? details : main)[k] = v;
  return { main, details };
}
