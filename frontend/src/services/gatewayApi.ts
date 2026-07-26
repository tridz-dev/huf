import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';

export type GatewayProvider = 'Telegram' | 'Slack' | 'Email' | 'WhatsApp';

export interface GatewayDoc {
  name: string;
  gateway_name: string;
  provider: GatewayProvider;
  is_enabled: 0 | 1;
  access_policy: 'Deny by default' | 'Allow list' | 'Pairing';
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
      'name', 'gateway_name', 'provider', 'is_enabled', 'access_policy', 'description',
      'default_target_type', 'default_agent', 'default_flow', 'last_event_at', 'last_error',
    ],
    orderBy: { field: 'modified', order: 'desc' },
    limit: 100,
  })) as GatewayDoc[];
}
