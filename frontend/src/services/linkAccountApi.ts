import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface SelfLinkPreview {
  gateway: string;
  team_id: string;
  external_id: string;
  user: string;
  slack_label: string;
  workspace_label: string;
}

export interface SelfLinkResult {
  linked: boolean;
  pending?: boolean;
  user: string;
}

// Signed token: base64url body, a dot, then a hex HMAC.
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{8,2048}\.[0-9a-f]{64}$/;

/** Reads the link token from a query string; returns null when absent or malformed. */
export function parseLinkToken(search: string): string | null {
  const token = new URLSearchParams(search).get('token')?.trim() ?? '';
  return TOKEN_PATTERN.test(token) ? token : null;
}

/** Plain-language message for a failed preview or confirm call. */
export function describeLinkError(error: unknown): string {
  const raw = error instanceof Error ? error.message : '';
  const text = raw.replace(/<[^>]*>/g, '').trim();
  if (/already linked/i.test(text)) {
    return 'This Slack account is already linked to another Huf user.';
  }
  if (/log in/i.test(text)) {
    return 'Log in to Huf with your own account to link it.';
  }
  return 'This link is invalid, expired, or has already been used. Ask Huf for a new one in Slack.';
}

export async function previewSelfLink(token: string): Promise<SelfLinkPreview> {
  try {
    const result = await call.get('huf.ai.gateways.identity.preview_self_link', { token });
    return result.message as SelfLinkPreview;
  } catch (error) {
    handleFrappeError(error, 'Error loading account link');
  }
}

export async function confirmSelfLink(token: string): Promise<SelfLinkResult> {
  try {
    const result = await call.post('huf.ai.gateways.identity.confirm_self_link', { token });
    return result.message as SelfLinkResult;
  } catch (error) {
    handleFrappeError(error, 'Error linking account');
  }
}
