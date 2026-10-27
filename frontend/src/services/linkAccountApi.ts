import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface SelfLinkPreview {
  gateway: string;
  team_id: string;
  external_id: string;
  user: string;
  slack_label?: string;
  person_label: string;
  workspace_label: string;
}

export type LinkProvider = 'slack' | 'teams';

const PROVIDER_ENDPOINTS: Record<LinkProvider, { module: string; preview: string; confirm: string }> = {
  slack: {
    module: 'Slack',
    preview: 'huf.ai.gateways.identity.preview_self_link',
    confirm: 'huf.ai.gateways.identity.confirm_self_link',
  },
  teams: {
    module: 'Teams',
    preview: 'huf.ai.gateways.teams_identity.preview_teams_link',
    confirm: 'huf.ai.gateways.teams_identity.confirm_teams_link',
  },
};

/** Reads the provider from `?p=`; anything other than `teams` means Slack. */
export function parseLinkProvider(search: string): LinkProvider {
  return new URLSearchParams(search).get('p') === 'teams' ? 'teams' : 'slack';
}

/** Display name of the chat app for a provider. */
export function providerName(provider: LinkProvider): string {
  return PROVIDER_ENDPOINTS[provider].module;
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
export function describeLinkError(error: unknown, provider: LinkProvider = 'slack'): string {
  const app = providerName(provider);
  const raw = error instanceof Error ? error.message : '';
  const text = raw.replace(/<[^>]*>/g, '').trim();
  if (/your huf account is already linked/i.test(text)) {
    return `Your Huf account is already linked to another ${app} account in this organisation.`;
  }
  if (/already linked/i.test(text)) {
    return `This ${app} account is already linked to another Huf user.`;
  }
  if (/log in/i.test(text)) {
    return 'Log in to Huf with your own account to link it.';
  }
  return `This link is invalid, expired, or has already been used. Ask Huf for a new one in ${app}.`;
}

export async function previewSelfLink(token: string, provider: LinkProvider = 'slack'): Promise<SelfLinkPreview> {
  try {
    const result = await call.get(PROVIDER_ENDPOINTS[provider].preview, { token });
    const data = result.message as SelfLinkPreview;
    return { ...data, person_label: data.person_label ?? data.slack_label ?? data.external_id };
  } catch (error) {
    handleFrappeError(error, 'Error loading account link');
  }
}

export async function confirmSelfLink(token: string, provider: LinkProvider = 'slack'): Promise<SelfLinkResult> {
  try {
    const result = await call.post(PROVIDER_ENDPOINTS[provider].confirm, { token });
    return result.message as SelfLinkResult;
  } catch (error) {
    handleFrappeError(error, 'Error linking account');
  }
}
