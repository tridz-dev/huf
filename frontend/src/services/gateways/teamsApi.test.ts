import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/frappe-error', () => ({ handleFrappeError: vi.fn() }));

import {
  buildLinkParams,
  buildPackageDownloadUrl,
  findCheck,
  isGuid,
  isValidPackageVersion,
  parseTenantText,
} from './teamsApi';

const A = '11111111-2222-3333-4444-555555555555';
const B = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE';

describe('teamsApi helpers', () => {
  it('validates GUIDs', () => {
    expect(isGuid(A)).toBe(true);
    expect(isGuid(` ${B} `)).toBe(true);
    expect(isGuid('contoso.onmicrosoft.com')).toBe(false);
    expect(isGuid(`{${A}}`)).toBe(false);
  });

  it('parses tenant text, de-duplicates, lowercases and reports invalid lines', () => {
    const r = parseTenantText(`${A}\n${B.toUpperCase()}, ${A}\n\nnope`);
    expect(r.tenants).toEqual([A, B.toLowerCase()]);
    expect(r.invalid).toEqual(['nope']);
  });

  it('checks package versions', () => {
    expect(isValidPackageVersion('1.0.0')).toBe(true);
    expect(isValidPackageVersion('1.0')).toBe(false);
  });

  it('shapes the download url', () => {
    const url = buildPackageDownloadUrl('My Gateway', ' 1.2.3 ');
    expect(url).toContain('teams.manifest.download_teams_app_package');
    expect(url).toContain('gateway_name=My+Gateway');
    expect(url).toContain('version=1.2.3');
    expect(buildPackageDownloadUrl('g', '')).toContain('version=1.0.0');
  });

  it('shapes link params', () => {
    expect(buildLinkParams('g', ` ${B} `, B, ' a@b.com ')).toEqual({
      gateway: 'g',
      tenant_id: B.toLowerCase(),
      aad_object_id: B.toLowerCase(),
      user: 'a@b.com',
    });
  });

  it('finds checks', () => {
    const d = {
      gateway: 'g',
      summary: { pass: 1, warn: 0, fail: 0, info: 0 },
      checks: [{ id: 'x', status: 'pass' as const, title: 'X', detail: '', how_to_fix: '' }],
    };
    expect(findCheck(d, 'x')?.title).toBe('X');
    expect(findCheck(null, 'x')).toBeUndefined();
  });
});
