import type { GatewayPolicy } from '@/services/gatewayApi';

// Providers where people connect their own account before anything runs, so an
// "Open" access policy is safe. Mirrors huf/ai/gateways/identity_policy.py.
const IDENTITY_PROVIDERS = new Set(['slack', 'microsoft teams']);

export const OPEN_POLICY_HELPER_TEXT =
  'Recommended for Slack and Teams: people connect their own account before anything runs.';

export function isIdentityProvider(provider?: string | null): boolean {
  return IDENTITY_PROVIDERS.has((provider ?? '').trim().toLowerCase());
}

/** Direct-message access policies the form may offer for a provider. */
export function directPolicyOptions(provider?: string | null): GatewayPolicy[] {
  const base: GatewayPolicy[] = ['Allow list', 'Pairing', 'Disabled'];
  return isIdentityProvider(provider) ? ['Open', ...base] : base;
}

/** Starting access policy for a newly created gateway. */
export function defaultDirectPolicy(provider?: string | null): GatewayPolicy {
  return isIdentityProvider(provider) ? 'Open' : 'Pairing';
}
