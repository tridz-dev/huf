import { describe, it, expect, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ db: {}, call: { get: vi.fn(), post: vi.fn() } }));

import { describeLinkError, parseLinkToken } from './linkAccountApi';

const SIG = 'a'.repeat(64);
const GOOD = `eyJnIjoiR1ctMSJ9.${SIG}`;

describe('parseLinkToken', () => {
  it('reads a well-formed token', () => {
    expect(parseLinkToken(`?token=${GOOD}`)).toBe(GOOD);
  });
  it('rejects missing, empty and malformed tokens', () => {
    expect(parseLinkToken('')).toBeNull();
    expect(parseLinkToken('?token=')).toBeNull();
    expect(parseLinkToken('?token=abc')).toBeNull();
    expect(parseLinkToken(`?token=<script>.${SIG}`)).toBeNull();
    expect(parseLinkToken(`?other=${GOOD}`)).toBeNull();
  });
});

describe('describeLinkError', () => {
  it('maps known failures to plain messages', () => {
    expect(describeLinkError(new Error('This Slack account is already linked to another user.'))).toMatch(
      /already linked/,
    );
    expect(describeLinkError(new Error('Log in to Huf with your own account to link it.'))).toMatch(/Log in/);
  });
  it('falls back to the expired-or-used message', () => {
    expect(describeLinkError(new Error('boom'))).toMatch(/expired, or has already been used/);
    expect(describeLinkError('x')).toMatch(/expired/);
  });
});
