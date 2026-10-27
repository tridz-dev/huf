import { describe, expect, it } from 'vitest';
import { defaultDirectPolicy, directPolicyOptions, isIdentityProvider } from './directPolicy';

describe('directPolicy', () => {
  it('offers Open only for Slack and Microsoft Teams', () => {
    expect(directPolicyOptions('Slack')).toContain('Open');
    expect(directPolicyOptions('Microsoft Teams')).toContain('Open');
    expect(directPolicyOptions(' microsoft teams ')).toContain('Open');
    for (const p of ['WhatsApp', 'Telegram', 'Discord', '', undefined, null]) {
      expect(directPolicyOptions(p)).not.toContain('Open');
    }
  });

  it('keeps the existing options for every provider', () => {
    expect(directPolicyOptions('Telegram')).toEqual(['Allow list', 'Pairing', 'Disabled']);
    expect(directPolicyOptions('Slack')).toEqual(['Open', 'Allow list', 'Pairing', 'Disabled']);
  });

  it('defaults new Slack and Teams gateways to Open, others to Pairing', () => {
    expect(defaultDirectPolicy('Slack')).toBe('Open');
    expect(defaultDirectPolicy('Microsoft Teams')).toBe('Open');
    expect(defaultDirectPolicy('WhatsApp')).toBe('Pairing');
    expect(isIdentityProvider('Slack')).toBe(true);
  });
});
