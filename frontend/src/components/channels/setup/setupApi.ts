import { call, db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { getGateway, updateGateway, type GatewayDoc, type GatewayPolicy } from '@/services/gatewayApi';
import {
  createIntegrationSetting,
  updateIntegrationSetting,
} from '@/services/integrationApi';

export interface WhatsAppCredentials {
  phone_number_id: string;
  business_account_id: string;
  app_id: string;
  access_token: string;
  app_secret: string;
  webhook_verify_token: string;
}

export type SaveResult = { ok: true; gateway: string } | { ok: false; error: string };

/** A hard-to-guess phrase to paste into Meta as the verify token. */
export function generateVerifyToken(): string {
  const bytes = new Uint8Array(12);
  (globalThis.crypto ?? window.crypto).getRandomValues(bytes);
  return 'huf-' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

function rows(c: WhatsAppCredentials) {
  return Object.entries(c).map(([key, value]) => ({ key, value: value.trim() }));
}

/**
 * Save WhatsApp credentials through the plain UI path (Integration Settings + Gateway docs;
 * plaintext is allowed here, never from an agent). `gateway` set: update that gateway's
 * credential record (creating one if it has none). Unset: create a new gateway named `name`.
 */
export async function saveWhatsAppCredentials(args: {
  gateway?: string;
  name?: string;
  credentials: WhatsAppCredentials;
  executionUser?: string;
}): Promise<SaveResult> {
  const { gateway, name, credentials, executionUser } = args;
  try {
    const existing: GatewayDoc | null = gateway ? await getGateway(gateway) : null;
    let settings = existing?.integration_settings || '';
    if (settings) {
      await updateIntegrationSetting(settings, { is_active: 1, credentials: rows(credentials) as never });
    } else {
      const created = await createIntegrationSetting({
        service: 'whatsapp',
        is_active: 1,
        credentials: rows(credentials) as never,
      });
      settings = created.name;
    }
    if (existing) {
      await updateGateway(existing.name, { integration_settings: settings, is_enabled: 1 });
      return { ok: true, gateway: existing.name };
    }
    const created = (await db.createDoc(doctype.Gateway, {
      gateway_name: (name || '').trim(),
      provider: 'WhatsApp',
      is_enabled: 1,
      integration_settings: settings,
      // Safe default: strangers get a pairing code, the admin approves.
      direct_policy: 'Pairing',
      execution_user: executionUser,
    })) as GatewayDoc;
    return { ok: true, gateway: created.name };
  } catch (e) {
    return { ok: false, error: getFrappeErrorMessage(e) || 'Could not save the credentials.' };
  }
}

/** Bind the agent that answers this number (the Gateway's default target). */
export async function bindAgent(gateway: string, agent: string): Promise<SaveResult> {
  try {
    await updateGateway(gateway, { default_target_type: 'Agent', default_agent: agent, default_flow: '' });
    return { ok: true, gateway };
  } catch (e) {
    return { ok: false, error: getFrappeErrorMessage(e) || 'Could not save.' };
  }
}

export async function savePolicy(gateway: string, policy: GatewayPolicy): Promise<SaveResult> {
  try {
    await updateGateway(gateway, { direct_policy: policy });
    return { ok: true, gateway };
  } catch (e) {
    return { ok: false, error: getFrappeErrorMessage(e) || 'Could not save.' };
  }
}

/** Latest inbound text on this number, from the channel conversations list. */
export async function latestInboundText(gateway: string): Promise<string | null> {
  try {
    const res = await call.get('huf.ai.channels.api.list_conversations', { gateway, limit: 1 });
    const body = (res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res) as {
      success?: boolean;
      items?: { last_message_preview?: string | null }[];
    } | null;
    return body?.success ? (body.items?.[0]?.last_message_preview ?? null) : null;
  } catch {
    return null;
  }
}
