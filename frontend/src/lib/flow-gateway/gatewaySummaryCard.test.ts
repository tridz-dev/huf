import { describe, expect, it } from 'vitest';
import { gatewaySubtitle } from './gatewaySummary';

describe('gatewaySubtitle on the card', () => {
  it('compact (card) text is short and keeps the keyword', () => {
    const text = gatewaySubtitle('whatsapp' as never, { gateway: 'Demo WhatsApp (never sends)', params: [{ key: 'keywords', value: ['order'] }] } as never, null, true);
    expect(text).toBe('Demo WhatsApp · Contains "order"');
    expect(text.length).toBeLessThan(48);
  });
  it('reads channel, then the filter, with the keyword quoted', () => {
    const text = gatewaySubtitle('whatsapp' as never, { gateway: 'g1', params: [{ key: 'keywords', value: ['order'] }] } as never, [{ name: 'g1', title: 'Demo WhatsApp (never sends)' }] as never);
    expect(text).toContain('Only messages that contain "order"');
    expect(text).toContain(' · ');
  });
});

describe('gatewaySubtitle on the card without a filter', () => {
  it('drops the channel word and the note after the name', () => {
    const text = gatewaySubtitle('whatsapp' as never, { gateway: 'Demo WhatsApp (never sends)', params: [] } as never, null, true);
    expect(text).toBe('When someone messages Demo WhatsApp');
  });
});
