import { describe, expect, it } from 'vitest';
import { gatewayErrorText, isTokenRejected } from './gatewayErrorCopy';

describe('gatewayErrorText', () => {
  it('never shows the raw Meta token error', () => {
    const raw = '(#190) Invalid OAuth access token - Cannot parse access token';
    expect(isTokenRejected(raw)).toBe(true);
    expect(gatewayErrorText(raw)).toBe('Meta rejected the access token. Replace it in settings.');
  });
  it('maps known codes and falls back to a short generic message', () => {
    expect(gatewayErrorText('(#131047) Re-engagement message')).toMatch(/24-hour/);
    expect(gatewayErrorText('Traceback (most recent call last) boom')).toBe('The last message ran into an error.');
    expect(gatewayErrorText('')).toBe('');
  });
});
