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
  /** Structured messaging endpoint URL (teams-messaging-endpoint item); preferred over parsing the hint. */
  endpoint_url?: string | null;
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
    body: 'Paste them into this gateway\'s credentials. Use the secret value (shown once in Azure), not the secret ID. The app password is write-only: Huf never shows it again after saving.',
    checkId: 'teams-credentials',
  },
  {
    id: 'endpoint',
    title: 'Paste the messaging endpoint into Azure',
    body: 'In the Azure Bot Configuration, set Messaging endpoint to the URL below. It must be HTTPS and publicly reachable. Huf cannot check what is set in Azure, so confirm it manually.',
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

/** Readiness check that carries the backend-built messaging endpoint URL in its hint. */
export const TEAMS_ENDPOINT_CHECK_ID = 'teams-messaging-endpoint';

/**
 * Extract the backend public messaging-endpoint URL from the readiness hint
 * ("Paste <url> as the Messaging endpoint ..."). Null unless it is absolute.
 */
export function endpointFromChecks(checks: ReadinessCheckLike[] | null | undefined): string | null {
  const item = (checks ?? []).find((c) => c.id === TEAMS_ENDPOINT_CHECK_ID);
  const structured = typeof item?.endpoint_url === 'string' ? item.endpoint_url.trim() : '';
  if (/^https?:\/\/\S+$/i.test(structured)) return structured;
  const hint = item?.hint ?? '';
  const m = /Paste (https?:\/\/\S+) as the Messaging endpoint/.exec(hint);
  return m ? m[1] : null;
}

/** True when the endpoint check is not done and its hint says the URL must be public https. */
export function endpointNeedsPublicHttps(checks: ReadinessCheckLike[] | null | undefined): boolean {
  const item = (checks ?? []).find((c) => c.id === TEAMS_ENDPOINT_CHECK_ID);
  return Boolean(item && !item.done && /public\s+https/i.test(item.hint ?? ''));
}

export const TEAMS_PUBLIC_HTTPS_WARNING =
  'Azure only accepts a public https messaging endpoint. Set a public https site URL (host_name) before pasting it into Azure.';
export const TEAMS_UNSAVED_REASON = 'Save the gateway first: these actions need a saved gateway.';
export const TEAMS_DISABLED_NOTE = 'This gateway is disabled, so the bot will not answer messages until you enable it.';
export const TEAMS_FORBIDDEN_NOTICE = 'You only have read-only access to this gateway. Ask a Gateway administrator to do this.';

/** True when an API error is a permission denial (HTTP 403 / PermissionError). */
export function isForbiddenError(e: unknown): boolean {
  const err = e as Record<string, unknown> | null | undefined;
  if (!err || typeof err !== 'object') return false;
  const resp = err.response as Record<string, unknown> | undefined;
  const status = err.httpStatus ?? err.status ?? err.statusCode ?? resp?.status;
  if (Number(status) === 403) return true;
  const hay = [err.exc_type, err.exception, (err.originalError as Record<string, unknown> | undefined)?.exc_type]
    .filter((v) => v != null)
    .map((v) => String(typeof v === 'string' ? v : JSON.stringify(v)))
    .join(' ');
  return /PermissionError/i.test(hay);
}

export const TEAMS_PERMISSION_NOTES: string[] = [
  'In personal chats the bot receives every message sent to it.',
  'In group chats and channels the bot only receives messages that @mention it, unless the app has resource-specific consent (RSC) for that scope.',
  'No Microsoft Graph admin consent is required for plain bot messaging (verify in your tenant).',
  'Uploading a custom app needs the custom app upload policy, or a Teams admin to upload it (verify in your tenant).',
  'Teams test send needs a conversation: message the bot first.',
];

export const TEAMS_RATE_LIMIT_NOTICE = 'Verify connection was run moments ago. Wait a few seconds and try again.';
export const TEAMS_VERIFY_COOLDOWN_MS = 5000;
export const TEAMS_REVOKE_DELAY_MS = 1000;
export const TEAMS_PACKAGE_DECODE_ERROR = 'The Teams app package could not be read. Try downloading it again.';
export const TEAMS_READINESS_UNAVAILABLE = 'Could not load setup status. Steps are shown as "Check manually".';

/** True when an API error is the backend rate limit (HTTP 429 / TooManyRequestsError). */
export function isRateLimitError(e: unknown): boolean {
  const err = e as Record<string, unknown> | null | undefined;
  if (!err || typeof err !== 'object') return false;
  const resp = err.response as Record<string, unknown> | undefined;
  const status = err.httpStatus ?? err.status ?? err.statusCode ?? resp?.status;
  if (Number(status) === 429) return true;
  const hay = [err.exc_type, err.exception, err.message, (err.originalError as Record<string, unknown> | undefined)?.exc_type, err._server_messages]
    .filter((v) => v != null)
    .map((v) => (typeof v === 'string' ? v : JSON.stringify(v)))
    .join(' ');
  return /TooManyRequests|moments ago/i.test(hay);
}

/**
 * Map a backend error from the manifest endpoint to a friendly message. The site-config keys are optional
 * overrides now; the server message (e.g. "set a public https site URL") is already actionable, so show it.
 */
export function mapManifestError(message: string | null | undefined): string {
  return (message ?? '').trim() || 'Failed to generate the Teams app package.';
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
