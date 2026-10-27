import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface SlackSetupCheck {
  id: string;
  ok: boolean;
  plain_title: string;
  detail: string;
  how_to_fix: string;
  informational?: boolean;
}

export interface SlackSetupStatus {
  verified: boolean;
  checked_at?: string | null;
  checks: SlackSetupCheck[];
  request_url_verified: boolean;
}

export interface SlackTestMessageTarget {
  slackUserId?: string;
  email?: string;
}

const METHOD_BASE = 'huf.ai.gateways.slack_setup';

export async function getSlackManifest(gatewayName: string): Promise<Record<string, unknown>> {
  try {
    const result = await call.get(`${METHOD_BASE}.get_slack_manifest`, { gateway_name: gatewayName });
    return result.message as Record<string, unknown>;
  } catch (error) {
    handleFrappeError(error, 'Error preparing the Slack app manifest');
  }
}

export async function verifySlackSetup(gatewayName: string): Promise<SlackSetupCheck[]> {
  try {
    const result = await call.post(`${METHOD_BASE}.verify_slack_setup`, { gateway_name: gatewayName });
    return (result.message as SlackSetupCheck[]) || [];
  } catch (error) {
    handleFrappeError(error, 'Error checking the Slack connection');
  }
}

export async function getSlackSetupStatus(gatewayName: string): Promise<SlackSetupStatus> {
  try {
    const result = await call.get(`${METHOD_BASE}.get_slack_setup_status`, { gateway_name: gatewayName });
    return result.message as SlackSetupStatus;
  } catch (error) {
    handleFrappeError(error, 'Error loading the Slack setup status');
  }
}

export async function sendSlackTestMessage(
  gatewayName: string,
  target: SlackTestMessageTarget
): Promise<{ ok: boolean }> {
  try {
    const result = await call.post(`${METHOD_BASE}.send_test_dm`, {
      gateway_name: gatewayName,
      slack_user_id: target.slackUserId || undefined,
      email: target.email || undefined,
    });
    return result.message as { ok: boolean };
  } catch (error) {
    handleFrappeError(error, 'Error sending the Slack test message');
  }
}
