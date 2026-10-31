// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { nodeKind, validateNode } from './flowValidation';
import { FIXTURE_REGISTRY } from '../flow-gateway/registryFixture';
import { setGatewayRegistry } from '../flow-gateway/registryStore';

const node = (triggerConfig: Record<string, unknown>) => ({ id: 't', data: { label: 'WhatsApp message', nodeType: 'trigger', triggerConfig } });
afterEach(() => setGatewayRegistry(null));

describe('chat trigger validation', () => {
  it('maps each kind to its contract node type', () => {
    expect(nodeKind(node({ type: 'gateway' }))).toBe('trigger.gateway');
    expect(nodeKind(node({ type: 'whatsapp' }))).toBe('trigger.whatsapp');
    expect(nodeKind(node({ type: 'telegram' }))).toBe('trigger.telegram');
    expect(nodeKind(node({ type: 'webhook' }))).toBe('trigger.webhook');
    expect(nodeKind(node({}))).toBe('trigger.unset');
    expect(nodeKind(node({ type: 'mystery' }))).toBe('trigger.unset');
  });

  it('a blank channel is something to finish, in plain words, before the registry has loaded', () => {
    const issues = validateNode(node({ type: 'whatsapp' }), []);
    expect(issues).toHaveLength(1);
    expect(issues[0]).toMatchObject({ field: 'gateway', kind: 'trigger.whatsapp', message: 'Pick a WhatsApp number.' });
    expect(validateNode(node({ type: 'telegram', gateway: '' }), [])[0].message).toBe('Pick a Telegram bot.');
  });

  it('is clean once a channel is chosen', () => {
    expect(validateNode(node({ type: 'whatsapp', gateway: 'Support WhatsApp' }), [])).toEqual([]);
  });

  it('uses the loaded registry to check the channel kind and the options', () => {
    setGatewayRegistry(FIXTURE_REGISTRY);
    expect(validateNode(node({ type: 'whatsapp', gateway: 'Sales Bot' }), [])[0].message).toContain('not a WhatsApp number');
    const bad = validateNode(node({ type: 'whatsapp', gateway: 'Support WhatsApp', params: [{ key: 'keywords', value: 'x' }] }), []);
    expect(bad.map((i) => i.field)).toEqual(['params.keywords']);
  });
});
