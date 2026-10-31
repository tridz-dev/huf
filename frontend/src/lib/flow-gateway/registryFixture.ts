import type { GatewayParamSpec, GatewayPayloadField, GatewayRegistry, GatewayTriggerNodeType, GatewayTriggerSpec } from './gatewayTrigger.types';

/**
 * A small registry in the shape the server serves. Used by the mock API and by tests, so the editor can be exercised
 * without a bench. It is not the real registry: the server's `registry_snapshot.json` is.
 */
const param = (p: Partial<GatewayParamSpec> & Pick<GatewayParamSpec, 'key' | 'label' | 'type'>): GatewayParamSpec => ({
  help: '', options: [], required: false, default: null, multiple: false, show_when: null, section: 'setup', ...p,
});
const field = (name: string, label: string, sample: unknown, extra: Partial<GatewayPayloadField> = {}): GatewayPayloadField => ({
  path: `input.${name}`, label, type: 'text', sample, customer_provided: false, sensitive: false, advanced: false, ...extra,
});

const KINDS = [
  { value: 'text', label: 'Text' }, { value: 'image', label: 'Photo' }, { value: 'voice', label: 'Voice note' }, { value: 'document', label: 'File' },
];
const GENERIC_PARAMS = [
  param({ key: 'only_senders', label: 'Only these people', type: 'people', help: 'Leave empty to answer everyone the channel lets in.' }),
  param({ key: 'message_kinds', label: 'Only these kinds of message', type: 'multiselect', options: KINDS, help: 'Leave empty for every kind.' }),
  param({ key: 'keywords', label: 'Only messages that contain', type: 'tags', help: 'Any of these words. Capital letters do not matter.' }),
  param({ key: 'starts_with', label: 'Only messages that start with', type: 'text' }),
  param({ key: 'chat_scope', label: 'Where', type: 'select', default: 'both', options: [{ value: 'direct', label: 'One-to-one chats' }, { value: 'groups', label: 'Groups' }, { value: 'both', label: 'Both' }] }),
  param({ key: 'only_when_mentioned', label: 'Only when the bot is mentioned', type: 'boolean', default: false, show_when: { key: 'chat_scope', in: ['groups', 'both'] } }),
  param({ key: 'has_attachment', label: 'Only messages with a file', type: 'boolean', default: false }),
  param({ key: 'ignore_bots', label: 'Ignore messages from other bots', type: 'boolean', default: true }),
  param({ key: 'max_runs_per_sender_per_hour', label: 'Most runs per person per hour', type: 'number', default: 30, section: 'more', help: 'Further messages from the same person that hour are skipped.' }),
  param({ key: 'allow_parallel', label: 'Handle several messages from one chat at the same time', type: 'boolean', default: false, section: 'more' }),
];
const GENERIC_FIELDS = [
  field('text', 'Message text', 'Hi, is my order ready?', { customer_provided: true }),
  field('display_name', 'Sender name', 'Asha', { customer_provided: true }),
  field('message_type', 'Kind of message', 'text'),
  field('attachments', 'Files', [], { type: 'list' }),
  field('received_at', 'Received at', '2026-01-15 17:15:00', { type: 'datetime' }),
  field('is_room', 'In a group', false, { type: 'yes_no' }),
  field('sender_id', 'Sender id', '15550001111', { advanced: true, sensitive: true }),
  field('conversation_id', 'Conversation id', '15550001111', { advanced: true }),
  field('gateway_event', 'Message record', 'GWE-0001', { advanced: true }),
];
const SAMPLE = { text: 'Hi, is my order ready?', display_name: 'Asha', message_type: 'text', attachments: [], received_at: '2026-01-15 17:15:00', is_room: false, sender_id: '15550001111' };

const spec = (nodeType: GatewayTriggerNodeType, provider: string, label: string, params: GatewayParamSpec[], fields: GatewayPayloadField[]): GatewayTriggerSpec => ({
  provider, label, node_type: nodeType, event_kinds: [{ value: 'message', label: 'A message' }], params, payload_fields: fields, sample_payload: SAMPLE,
});

export const FIXTURE_REGISTRY: GatewayRegistry = {
  version: 1,
  limits: { max_params: 40, max_list_items: 50, max_text: 500, max_item_text: 200 },
  specs: {
    'trigger.gateway': spec('trigger.gateway', '', 'Chat', GENERIC_PARAMS, GENERIC_FIELDS),
    'trigger.whatsapp': spec('trigger.whatsapp', 'WhatsApp', 'WhatsApp',
      [...GENERIC_PARAMS.filter((p) => !['chat_scope', 'only_when_mentioned'].includes(p.key)),
        param({ key: 'button_reply_ids', label: 'Only when they press this button', type: 'tags' }),
        param({ key: 'first_message_only', label: 'Only their first message', type: 'boolean', default: false })],
      [...GENERIC_FIELDS, field('button_title', 'Button chosen', ''), field('referral', 'Ad details', '', { type: 'record' })]),
    'trigger.telegram': spec('trigger.telegram', 'Telegram', 'Telegram',
      [...GENERIC_PARAMS, param({ key: 'commands', label: 'Only these commands', type: 'tags', help: 'For example /start.' }),
        param({ key: 'include_edits', label: 'Also start when a message is edited', type: 'boolean', default: false, section: 'more' })],
      [...GENERIC_FIELDS, field('command', 'Command', ''), field('command_args', 'Text after the command', '', { customer_provided: true })]),
  },
  gateways: [
    { name: 'Support WhatsApp', label: 'Support', provider: 'WhatsApp', enabled: true, connection_state: 'connected' },
    { name: 'Sales Bot', label: 'Sales Bot', provider: 'Telegram', enabled: true, connection_state: 'connected' },
    { name: 'Team Slack', label: 'Team chat', provider: 'Slack', enabled: true, connection_state: 'connected' },
  ],
};
