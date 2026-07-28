import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';

// TODO(#473-followup): The consolidated gateway DocType uses per-channel admission
// fields (direct_policy, room_policy, room_sender_policy, mention_required,
// pairing_ttl_minutes) instead of the older access_policy. Keep this file in sync
// with huf/huf/doctype/gateway/gateway.json. See docs/gateway-todo.md.
export type GatewayProvider =
  | 'WhatsApp'
  | 'Messenger'
  | 'Instagram'
  | 'Telegram'
  | 'Slack'
  | 'Discord'
  | 'Email'
  | 'SMS'
  | 'Google Chat'
  | 'VK'
  | 'WeCom'
  | 'Microsoft Teams';

export type GatewayPolicy = 'Disabled' | 'Pairing' | 'Allow list' | 'Open';

export interface GatewayDoc {
  name: string;
  gateway_name: string;
  provider: GatewayProvider;
  is_enabled: 0 | 1;
  execution_user?: string;
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
      'name', 'gateway_name', 'provider', 'is_enabled', 'execution_user',
      'direct_policy', 'room_policy', 'room_sender_policy',
      'mention_required', 'pairing_ttl_minutes', 'description',
      'default_target_type', 'default_agent', 'default_flow', 'last_event_at', 'last_error',
    ],
    orderBy: { field: 'modified', order: 'desc' },
    limit: 100,
  })) as GatewayDoc[];
}

export async function updateGateway(name: string, data: Partial<GatewayDoc>): Promise<GatewayDoc> {
  return (await db.updateDoc(doctype.Gateway, name, data)) as GatewayDoc;
}

export async function deleteGateway(name: string): Promise<void> {
  await db.deleteDoc(doctype.Gateway, name);
}

export async function getAvailableAgents(): Promise<{ name: string; agent_name: string }[]> {
  try {
    const list = await db.getDocList(doctype.Agent, {
      fields: ['name', 'agent_name'],
      limit: 100,
    });
    return list.map((item: any) => ({
      name: item.name,
      agent_name: item.agent_name || item.name,
    }));
  } catch {
    return [];
  }
}

export async function getAvailableFlows(): Promise<{ name: string; title: string }[]> {
  try {
    const list = await db.getDocList('Flow Definition', {
      fields: ['name', 'title'],
      limit: 100,
    });
    return list.map((item: any) => ({
      name: item.name,
      title: item.title || item.name,
    }));
  } catch {
    return [];
  }
}
