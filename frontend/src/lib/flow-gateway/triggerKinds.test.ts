import { describe, expect, it } from 'vitest';
import { GATEWAY_TRIGGER_KINDS, gatewayKindForNodeType, isGatewayTriggerNodeType } from './triggerKinds';

describe('triggerKinds', () => {
  it('lists the three chat trigger node types once each', () => {
    expect(GATEWAY_TRIGGER_KINDS.map((k) => k.nodeType)).toEqual(['trigger.gateway', 'trigger.whatsapp', 'trigger.telegram']);
  });

  it('ties dedicated kinds to their provider and leaves the generic one open', () => {
    expect(gatewayKindForNodeType('trigger.whatsapp')?.provider).toBe('WhatsApp');
    expect(gatewayKindForNodeType('trigger.telegram')?.provider).toBe('Telegram');
    expect(gatewayKindForNodeType('trigger.gateway')?.provider).toBeNull();
  });

  it('does not claim other triggers', () => {
    expect(isGatewayTriggerNodeType('trigger.webhook')).toBe(false);
    expect(isGatewayTriggerNodeType('trigger.whatsapp')).toBe(true);
  });
});
