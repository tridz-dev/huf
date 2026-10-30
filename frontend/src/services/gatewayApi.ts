import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';

// TODO(#473-followup): The consolidated gateway DocType uses per-channel admission
// fields (direct_policy, room_policy, room_sender_policy, mention_required,
// pairing_ttl_minutes) instead of the older access_policy. Keep this file in sync
// with huf/huf/doctype/gateway/gateway.json.
export type GatewayProvider =
  | 'WhatsApp'
  | 'Messenger'
  | 'Instagram'
  | 'Telegram'
  | 'Slack'
  | 'Email'
  | 'Google Chat'
  | 'Microsoft Teams';

export type GatewayPolicy = 'Disabled' | 'Pairing' | 'Allow list' | 'Open';

export interface GatewayDoc {
  name: string;
  gateway_name: string;
  provider: GatewayProvider;
  is_enabled: 0 | 1;
  execution_user?: string;
  integration_settings?: string;
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
  connection_state?: 'Connected' | 'Degraded' | 'Disconnected';
  connection_reason?: string;
  // Slack only
  unmapped_policy?: 'Ask to link account' | 'Use service user';
  private_reply_policy?: 'Reply where asked' | 'Private when marked sensitive' | 'Always private';
  show_feedback_buttons?: 0 | 1;
  // Access (Pairing)
  pairing_reply_enabled?: 0 | 1;
  pairing_pending_limit?: number;
  pairing_reply_daily_limit?: number;
  // WhatsApp only
  phone_number_id?: string;
  whatsapp_account?: string;
  whatsapp_business_account_id?: string;
  inbound_sender_limit?: number;
  opt_out_keywords?: string;
  opt_in_keywords?: string;
  opt_out_reply_text?: string;
  fallback_template?: string;
  fallback_template_language?: string;
  fallback_template_params?: string;
  preview_url?: 'Default (off)' | 'On' | 'Off';
  voice_reply_mode?: 'Off' | 'Voice only' | 'Text and voice';
  typing_indicator?: 0 | 1;
  error_reply_text?: string;
  retry_max_attempts?: number;
  agent_allow_proactive?: 0 | 1;
  agent_allow_template_management?: 0 | 1;
  agent_auto_submit_templates?: 0 | 1;
  agent_recipient_scope?: 'Current contact' | 'Allow-list' | 'Approved contacts' | 'Any number';
  agent_recipient_allowlist?: string;
  agent_send_cap_per_run?: number;
  agent_send_cap_per_day?: number;
  calling_enabled?: 0 | 1;
  call_greeting_audio?: string;
  call_reply_audio?: string;
  call_closing_audio?: string;
  call_max_seconds?: number;
  pin_ttl_hours?: number;
  keyword_beats_pin?: 0 | 1;
}

/** Every editable WhatsApp-only Gateway field, saved together from the Channel tab. */
export const WHATSAPP_GATEWAY_FIELDS = [
  'inbound_sender_limit', 'opt_out_keywords', 'opt_in_keywords', 'opt_out_reply_text',
  'fallback_template', 'fallback_template_language', 'fallback_template_params',
  'preview_url', 'voice_reply_mode', 'typing_indicator', 'error_reply_text', 'retry_max_attempts',
  'agent_allow_proactive', 'agent_allow_template_management', 'agent_auto_submit_templates',
  'agent_recipient_scope', 'agent_recipient_allowlist', 'agent_send_cap_per_run', 'agent_send_cap_per_day',
  'calling_enabled', 'call_greeting_audio', 'call_reply_audio', 'call_closing_audio', 'call_max_seconds',
  'pin_ttl_hours', 'keyword_beats_pin', 'whatsapp_business_account_id',
] as const satisfies readonly (keyof GatewayDoc)[];

/** The full Gateway record (every field), for editors that show more than the list columns. */
export async function getGateway(name: string): Promise<GatewayDoc> {
  return (await db.getDoc(doctype.Gateway, name)) as GatewayDoc;
}

export interface ChannelAgentConnection {
  service: string;
  provider: string | null;
  gateways: Pick<GatewayDoc, 'name' | 'is_enabled' | 'default_target_type' | 'default_agent' | 'default_flow'>[];
}

export interface ConnectAgentResult {
  gateway: string;
  created: boolean;
  enabled: boolean;
  enable_error: string;
  previous_agent: string | null;
  tools_added: number;
}

/** Which gateways use a channel credential and the agent each one answers with. */
export async function getChannelAgentConnection(integrationSettings: string): Promise<ChannelAgentConnection> {
  const result = await call.get('huf.ai.gateway_core.agent_connect.get_channel_agent_connection', {
    integration_settings: integrationSettings,
  });
  return result.message as ChannelAgentConnection;
}

/** Make an agent answer a channel: sets the gateway's default agent (creating the gateway if needed). */
export async function connectAgentToChannel(params: {
  integrationSettings: string;
  agent: string;
  gatewayName?: string;
}): Promise<ConnectAgentResult> {
  const result = await call.post('huf.ai.gateway_core.agent_connect.connect_agent_to_channel', {
    integration_settings: params.integrationSettings,
    agent: params.agent,
    gateway_name: params.gatewayName,
  });
  return result.message as ConnectAgentResult;
}

export async function getGateways(): Promise<GatewayDoc[]> {
  return (await db.getDocList(doctype.Gateway, {
    fields: [
      'name', 'gateway_name', 'provider', 'is_enabled', 'execution_user', 'integration_settings',
      'direct_policy', 'room_policy', 'room_sender_policy',
      'mention_required', 'pairing_ttl_minutes', 'description',
      'default_target_type', 'default_agent', 'default_flow', 'last_event_at', 'last_error',
      'connection_state', 'connection_reason',
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

export interface GatewayReadinessCheck {
  id: string;
  label: string;
  done: boolean;
  hint: string | null;
}

export interface GatewayReadinessPreview {
  ready: boolean;
  blocking_count: number;
  checks: GatewayReadinessCheck[];
}

// GW-15: server-verified readiness. Mirrors Gateway.validate() by calling the
// same dry-run backend endpoint (huf.ai.gateway_service.preview_gateway_readiness)
// so the frontend never has to re-encode (and drift from) those rules.
export async function getGatewayReadinessPreview(gatewayName: string): Promise<GatewayReadinessPreview> {
  const response = await call.get('huf.ai.gateway_service.preview_gateway_readiness', {
    gateway_name: gatewayName,
  });
  return (response.message ?? response) as GatewayReadinessPreview;
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
