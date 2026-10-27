import { describe, expect, it } from 'vitest';
import {
  base64ToBlob,
  base64ToBytes,
  deriveStepStates,
  endpointFromChecks,
  endpointNeedsPublicHttps,
  isForbiddenError,
  isRateLimitError,
  isGuid,
  isTeamsService,
  mapManifestError,
  normalizeVerifyResult,
  parseTenantList,
  teamsCredentialHint,
  teamsTestSendNote,
} from './teamsOnboarding';

const G = '123e4567-e89b-12d3-a456-426614174000';

describe('GUID helpers', () => {
  it('validates GUIDs', () => {
    expect(isGuid(G)).toBe(true);
    expect(isGuid(` ${G.toUpperCase()} `)).toBe(true);
    expect(isGuid('nope')).toBe(false);
    expect(isGuid('')).toBe(false);
    expect(isGuid(undefined)).toBe(false);
  });
  it('hints for app_id / tenant_id / allowed_tenant_ids', () => {
    expect(teamsCredentialHint('app_id', G)).toBeNull();
    expect(teamsCredentialHint('tenant_id', 'abc')).toMatch(/GUID/);
    expect(teamsCredentialHint('tenant_id', '')).toBeNull();
    expect(teamsCredentialHint('allowed_tenant_ids', `${G}, x ; ${G}`)).toMatch(/1 entry is not a GUID/);
    expect(teamsCredentialHint('allowed_tenant_ids', 'a,b')).toMatch(/2 entries are not a GUID/);
    expect(teamsCredentialHint('allowed_tenant_ids', `${G},${G}`)).toBeNull();
    expect(teamsCredentialHint('app_password', 'anything')).toBeNull();
  });
  it('parses tenant lists', () => {
    expect(parseTenantList(` a,b ;c\nd,, `)).toEqual(['a', 'b', 'c', 'd']);
    expect(parseTenantList(null)).toEqual([]);
  });
  it('detects teams services', () => {
    expect(isTeamsService('microsoft_teams')).toBe(true);
    expect(isTeamsService('whatsapp')).toBe(false);
  });
});

describe('deriveStepStates', () => {
  it('is manual for check-driven steps when no readiness data', () => {
    const s = deriveStepStates(null);
    expect(Object.values(s).every((v) => v === 'manual')).toBe(true);
  });
  it('maps readiness checks to steps', () => {
    const s = deriveStepStates([
      { id: 'teams-credentials', done: true },
      { id: 'teams-messaging-endpoint', done: false, hint: 'x' },
      { id: 'teams-first-message', done: false },
    ]);
    expect(s.credentials).toBe('done');
    expect(s.endpoint).toBe('manual'); // cannot be verified from Huf
    expect(s['first-message']).toBe('todo');
    expect(s['create-bot']).toBe('manual');
    expect(s.sideload).toBe('manual');
  });
});

describe('mapManifestError', () => {
  it('passes the actionable server message through', () => {
    const m = 'The site URL (http://localhost) is not a public https URL. Set a public https site URL (host_name) or provide the site config key teams_app_website_url.';
    expect(mapManifestError(`  ${m} `)).toBe(m);
  });
  it('has a fallback', () => {
    expect(mapManifestError('')).toBe('Failed to generate the Teams app package.');
    expect(mapManifestError(null)).toBe('Failed to generate the Teams app package.');
  });
});

describe('base64', () => {
  it('decodes bytes and builds a zip blob', async () => {
    const b64 = Buffer.from([0x50, 0x4b, 3, 4, 255]).toString('base64');
    expect(Array.from(base64ToBytes(b64))).toEqual([0x50, 0x4b, 3, 4, 255]);
    const blob = base64ToBlob(b64);
    expect(blob.type).toBe('application/zip');
    expect(blob.size).toBe(5);
  });
  it('falls back to Buffer when atob is missing', () => {
    const orig = globalThis.atob;
    // @ts-expect-error simulate a runtime without atob
    globalThis.atob = undefined;
    try {
      expect(Array.from(base64ToBytes('AQID'))).toEqual([1, 2, 3]);
    } finally {
      globalThis.atob = orig;
    }
  });
});

describe('misc', () => {
  it('test-send note only for Teams', () => {
    expect(teamsTestSendNote('Microsoft Teams')).toMatch(/message the bot first/);
    expect(teamsTestSendNote('Telegram')).toBeNull();
  });
  it('normalizes verify payloads defensively', () => {
    expect(normalizeVerifyResult(null)).toEqual({ ok: false, steps: [], message: '' });
    const r = normalizeVerifyResult({ ok: true, message: 'm', steps: [{ id: 'token', label: 'Token', ok: true }, { id: 'x', ok: 0, detail: 'bad' }] });
    expect(r.steps[0].detail).toBeNull();
    expect(r.steps[1]).toEqual({ id: 'x', label: 'x', ok: false, detail: 'bad' });
  });
});

describe('isRateLimitError', () => {
  it('detects 429 / TooManyRequests / moments ago', () => {
    expect(isRateLimitError({ httpStatus: 429 })).toBe(true);
    expect(isRateLimitError({ response: { status: 429 } })).toBe(true);
    expect(isRateLimitError({ exc_type: 'TooManyRequestsError' })).toBe(true);
    expect(isRateLimitError({ _server_messages: '["{\\"message\\": \\"run moments ago\\"}"]' })).toBe(true);
    expect(isRateLimitError(new Error('Verify connection was run moments ago'))).toBe(true);
  });
  it('ignores other errors', () => {
    expect(isRateLimitError(new Error('nope'))).toBe(false);
    expect(isRateLimitError(null)).toBe(false);
    expect(isRateLimitError({ status: 500 })).toBe(false);
  });
});

describe('endpointFromChecks', () => {
  it('extracts only absolute URLs', () => {
    expect(endpointFromChecks([{ id: 'teams-messaging-endpoint', done: false, hint: 'Paste https://a.b/x?gateway_name=G as the Messaging endpoint of' }])).toBe('https://a.b/x?gateway_name=G');
    expect(endpointFromChecks([{ id: 'teams-messaging-endpoint', done: false, hint: 'Paste /api/x as the Messaging endpoint' }])).toBeNull();
    expect(endpointFromChecks(undefined)).toBeNull();
  });
});

describe('structured endpoint_url', () => {
  const hint = 'Paste https://hint.example/x as the Messaging endpoint';
  it('prefers endpoint_url over the hint', () => {
    expect(endpointFromChecks([{ id: 'teams-messaging-endpoint', done: false, hint, endpoint_url: 'https://struct.example/h?gateway_name=G' }])).toBe('https://struct.example/h?gateway_name=G');
  });
  it('falls back to the hint when endpoint_url is missing or not absolute', () => {
    expect(endpointFromChecks([{ id: 'teams-messaging-endpoint', done: false, hint }])).toBe('https://hint.example/x');
    expect(endpointFromChecks([{ id: 'teams-messaging-endpoint', done: false, hint, endpoint_url: '/relative' }])).toBe('https://hint.example/x');
    expect(endpointFromChecks([{ id: 'teams-messaging-endpoint', done: false, endpoint_url: null }])).toBeNull();
  });
});

describe('endpointNeedsPublicHttps / isForbiddenError', () => {
  it('only when not done and hint says public https', () => {
    expect(endpointNeedsPublicHttps([{ id: 'teams-messaging-endpoint', done: false, hint: 'It must be a public https URL' }])).toBe(true);
    expect(endpointNeedsPublicHttps([{ id: 'teams-messaging-endpoint', done: true, hint: 'public https' }])).toBe(false);
    expect(endpointNeedsPublicHttps([{ id: 'teams-messaging-endpoint', done: false, hint: 'Paste it' }])).toBe(false);
    expect(endpointNeedsPublicHttps(undefined)).toBe(false);
  });
  it('detects 403 and PermissionError', () => {
    expect(isForbiddenError({ httpStatus: 403 })).toBe(true);
    expect(isForbiddenError({ exc_type: 'PermissionError' })).toBe(true);
    expect(isForbiddenError({ httpStatus: 500 })).toBe(false);
    expect(isForbiddenError(null)).toBe(false);
  });
});
