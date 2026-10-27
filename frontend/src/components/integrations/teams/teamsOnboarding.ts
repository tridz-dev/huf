/**
 * Pure helpers for the Microsoft Teams onboarding UI (setup guide, manifest
 * download, verify connection). No React, no network. The server stays
 * authoritative; everything here is a client-side hint or presentation helper.
 */

export const TEAMS_PROVIDER = 'Microsoft Teams';

/** Integration Service ids that belong to the Teams gateway adapter. */
export function isTeamsService(service: unknown): boolean {
  return service === 'microsoft_teams' || service === 'teams';
}

const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isGuid(value: string | null | undefined): boolean {
  return GUID_RE.test((value ?? '').trim());
}

/** Split a comma/space/semicolon/newline separated tenant list. */
export function parseTenantList(raw: string | null | undefined): string[] {
  return (raw ?? '')
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Format hint for a Teams credential field, or null when the value looks fine
 * (or is empty, or the key is not a GUID field). Client-side only.
 */
export function teamsCredentialHint(key: string, value: string | null | undefined): string | null {
  const v = (value ?? '').trim();
  if (!v) return null;
  if (key === 'app_id' || key === 'tenant_id') {
    return isGuid(v) ? null : 'Expected a GUID like 00000000-0000-0000-0000-000000000000.';
  }
  if (key === 'allowed_tenant_ids') {
    const bad = parseTenantList(v).filter((t) => !isGuid(t));
    return bad.length ? `${bad.length} entr${bad.length === 1 ? 'y is' : 'ies are'} not a GUID.` : null;
  }
  return null;
}

export interface ReadinessCheckLike {
  id: string;
  label?: string;
  done: boolean;
  hint?: string | null;
}

export type StepState = 'done' | 'todo' | 'manual';

export interface TeamsStep {
  id: string;
  title: string;
  body: string;
  /** Readiness check id that drives this step's state; absent = cannot be detected. */
  checkId?: string;
}

export const TEAMS_STEPS: TeamsStep[] = [
  {
    id: 'create-bot',
    title: 'Create an Azure Bot (Single Tenant)',
    body: 'In the Azure portal create an Azure Bot resource with app type Single Tenant. Multi-tenant and managed identity bots are not supported.',
  },
  {
    id: 'credentials',
    title: 'Copy App ID, client secret value and Tenant ID',
    body: 'Paste them into this gateway\'s credentials. Use the secret value (shown once), not the secret ID.',
    checkId: 'teams-credentials',
  },
  {
    id: 'endpoint',
    title: 'Paste the messaging endpoint into Azure',
    body: 'In the Azure Bot Configuration, set Messaging endpoint to the URL below. It must be HTTPS and publicly reachable.',
    checkId: 'teams-messaging-endpoint',
  },
  {
    id: 'channel',
    title: 'Enable the Microsoft Teams channel',
    body: 'In the Azure Bot Channels, add Microsoft Teams and accept the terms. Without it Teams will not route messages to the bot.',
  },
  {
    id: 'package',
    title: 'Download the Teams app package',
    body: 'Use the download button below. The package manifest bot ID is this gateway\'s App ID.',
  },
  {
    id: 'sideload',
    title: 'Sideload the app in Teams',
    body: 'Teams, Apps, Manage your apps, Upload a custom app (needs the custom app upload policy), or upload it in the Teams admin center (verify in your tenant).',
  },
  {
    id: 'first-message',
    title: 'Message the bot first',
    body: 'Send the bot a message in a personal chat, or @mention it in a group chat or channel. Huf stores the conversation then; replies and test messages need it.',
    checkId: 'teams-first-message',
  },
];

export function deriveStepStates(checks: ReadinessCheckLike[] | null | undefined): Record<string, StepState> {
  const byId = new Map((checks ?? []).map((c) => [c.id, c]));
  const out: Record<string, StepState> = {};
  for (const step of TEAMS_STEPS) {
    const check = step.checkId ? byId.get(step.checkId) : undefined;
    out[step.id] = check ? (check.done ? 'done' : 'todo') : 'manual';
  }
  return out;
}

export const TEAMS_SITE_CONFIG_KEYS = [
  'teams_app_developer_name',
  'teams_app_website_url',
  'teams_app_privacy_url',
  'teams_app_terms_url',
] as const;

/**
 * Map a backend error from the manifest endpoint to a friendly message. When the
 * server complains about missing site-config keys, name the keys to set.
 */
export function mapManifestError(message: string | null | undefined): string {
  const raw = (message ?? '').trim();
  const mentioned = TEAMS_SITE_CONFIG_KEYS.filter((k) => raw.includes(k));
  if (mentioned.length > 0 || /site config key/i.test(raw)) {
    const keys = mentioned.length > 0 ? mentioned : TEAMS_SITE_CONFIG_KEYS;
    return `Cannot build the app package yet. Set ${keys.join(', ')} in the site config (site_config.json), then try again.`;
  }
  return raw || 'Failed to generate the Teams app package.';
}

/** Decode base64 into bytes using atob, falling back to Buffer (Node). */
export function base64ToBytes(b64: string): Uint8Array {
  if (typeof atob === 'function') {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }
  const B = (globalThis as { Buffer?: { from(s: string, enc: string): Uint8Array } }).Buffer;
  if (!B) throw new Error('No base64 decoder available');
  return new Uint8Array(B.from(b64, 'base64'));
}

export function base64ToBlob(b64: string, type = 'application/zip'): Blob {
  return new Blob([base64ToBytes(b64) as BlobPart], { type });
}

export function teamsTestSendNote(provider: string | undefined): string | null {
  return provider === TEAMS_PROVIDER
    ? 'Teams test send needs a conversation: message the bot first (personal chat, or @mention it in a group or channel). Use the ID of that conversation as the recipient.'
    : null;
}

export interface VerifyStep {
  id: string;
  label: string;
  ok: boolean;
  detail?: string | null;
}

export interface VerifyResult {
  ok: boolean;
  steps: VerifyStep[];
  message: string;
}

/** Defensive normalisation of the diagnostics payload. */
export function normalizeVerifyResult(raw: unknown): VerifyResult {
  const r = (raw ?? {}) as Partial<VerifyResult>;
  const steps = Array.isArray(r.steps)
    ? r.steps.map((s) => ({
        id: String(s?.id ?? ''),
        label: String(s?.label ?? s?.id ?? ''),
        ok: Boolean(s?.ok),
        detail: s?.detail == null ? null : String(s.detail),
      }))
    : [];
  return { ok: Boolean(r.ok), steps, message: String(r.message ?? '') };
}
