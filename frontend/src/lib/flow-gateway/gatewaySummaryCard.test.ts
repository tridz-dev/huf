import { describe, expect, it } from 'vitest';
import { gatewaySubtitle } from './gatewaySummary';

describe('gatewaySubtitle on the card', () => {
  it('reads channel, then the filter, with the keyword quoted', () => {
    const text = gatewaySubtitle('whatsapp' as never, { gateway: 'g1', params: [{ key: 'keywords', value: ['order'] }] } as never, [{ name: 'g1', title: 'Demo WhatsApp (never sends)' }] as never);
    expect(text).toContain('Only messages that contain "order"');
    expect(text).toContain(' · ');
  });
});
