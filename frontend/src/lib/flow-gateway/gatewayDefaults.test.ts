import { describe, expect, it } from 'vitest';
import { FIXTURE_REGISTRY } from './registryFixture';
import { newGatewayConfig, triggerIsConfigured } from './gatewayDefaults';

describe('newGatewayConfig', () => {
  it('picks the only number or bot of the kind for the person', () => {
    expect(newGatewayConfig('whatsapp', FIXTURE_REGISTRY.gateways)).toEqual({ type: 'whatsapp', gateway: 'Support WhatsApp' });
    expect(newGatewayConfig('telegram', FIXTURE_REGISTRY.gateways)).toEqual({ type: 'telegram', gateway: 'Sales Bot' });
  });
  it('leaves it blank when there are none, several, or the list is unknown', () => {
    expect(newGatewayConfig('whatsapp', [])).toEqual({ type: 'whatsapp' });
    expect(newGatewayConfig('whatsapp', undefined)).toEqual({ type: 'whatsapp' });
    expect(newGatewayConfig('gateway', FIXTURE_REGISTRY.gateways)).toEqual({ type: 'gateway' });
    const two = [...FIXTURE_REGISTRY.gateways, { ...FIXTURE_REGISTRY.gateways[0], name: 'Second' }];
    expect(newGatewayConfig('whatsapp', two)).toEqual({ type: 'whatsapp' });
  });
  it('does not pre-pick a switched off number', () => {
    expect(newGatewayConfig('whatsapp', [{ ...FIXTURE_REGISTRY.gateways[0], enabled: false }])).toEqual({ type: 'whatsapp' });
  });
});

describe('triggerIsConfigured', () => {
  it('needs a channel for a chat trigger and only a choice for the others', () => {
    expect(triggerIsConfigured({ type: 'whatsapp' })).toBe(false);
    expect(triggerIsConfigured({ type: 'whatsapp', gateway: 'Support WhatsApp' })).toBe(true);
    expect(triggerIsConfigured({ type: 'webhook' })).toBe(true);
    expect(triggerIsConfigured({ type: undefined })).toBe(false);
    expect(triggerIsConfigured(undefined)).toBe(false);
  });
});
