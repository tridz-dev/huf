import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';

// TODO(#473-followup): The consolidated gateway DocType uses per-channel admission
// fields (direct_policy, room_policy, room_sender_policy, mention_required,
// pairing_ttl_minutes) instead of the older access_policy. Keep this file in sync
// with huf/huf/doctype/gateway/gateway.json. See docs/gateway-todo.md.
export type GatewayProvider =
  | 'Telegram'
  | 'Slack'
  | 'Discord'
  | 'Email'
  | 'WhatsApp'
  | 'VK'
  | 'WeCom'
  | 'Microsoft Teams';

export type GatewayPolicy = 'Disabled' | 'Pairing' | 'Allow list' | 'Open';

export interface GatewayDoc {
  name: string;
  gateway_name: string;
  provider: GatewayProvider;
  is_enabled: 0 | 1;
  // TODO(#473-followup): admission UI is incomplete; direct_policy is shown as a
  // placeholder until the full admission form is built.
  direct_policy: GatewayPolicy;
  room_policy?: GatewayPolicy;
  room_sender_policy?: GatewayPolicy;
  mention_required?: 0 | 1;
  pairing_ttl_minutes?: number;
  description?: string;
  default_target_type?: '' | 'Agent' | 'Flow';
  default_agent?: string;
  default_flow?: string;
  last_event_at?: string;
  last_error?: string;
}

export async function getGateways(): Promise<GatewayDoc[]> {
  return (await db.getDocList(doctype.Gateway, {
    fields: [
      'name', 'gateway_name', 'provider', 'is_enabled',
      'direct_policy', 'room_policy', 'room_sender_policy',
      'mention_required', 'pairing_ttl_minutes', 'description',
      'default_target_type', 'default_agent', 'default_flow', 'last_event_at', 'last_error',
    ],
    orderBy: { field: 'modified', order: 'desc' },
    limit: 100,
  })) as GatewayDoc[];
}
