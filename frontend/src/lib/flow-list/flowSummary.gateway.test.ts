import { afterEach, describe, expect, it } from 'vitest';
import { generatedSummary, triggerLine, triggerPhrase } from './flowListSummary';
import { publishedToast, startSummary } from './flowPublishSummary';
import { FIXTURE_REGISTRY } from '../flow-gateway/registryFixture';
import { setGatewayRegistry } from '../flow-gateway/registryStore';

afterEach(() => setGatewayRegistry(null));

describe('list wording for chat triggers', () => {
  it('uses the label the server resolved, never the record name', () => {
    const t = { type: 'whatsapp' as const, gateway: 'GW-0007', gateway_label: 'Support' };
    expect(triggerPhrase(t)).toEqual({ text: 'someone messages Support on WhatsApp', scheduled: false });
    expect(triggerLine(t)).toBe('Starts when someone messages Support on WhatsApp');
    expect(generatedSummary({ trigger: t, step_count: 2 })).toBe('Starts when someone messages Support on WhatsApp, then 2 steps.');
  });
  it('a chat trigger with no channel still reads as a sentence', () => {
    expect(triggerLine({ type: 'telegram' })).toBe('Starts when someone messages you on Telegram');
  });
});

describe('publish wording for chat triggers', () => {
  it('names the channel once the registry is known', () => {
    setGatewayRegistry(FIXTURE_REGISTRY);
    const s = startSummary({ type: 'whatsapp', gateway: 'Support WhatsApp' }, 'f', 'https://x');
    expect(s).toEqual({ kind: 'chat', text: 'when someone messages Support on WhatsApp' });
    expect(publishedToast(s).description).toBe('It will now start by itself when someone messages Support on WhatsApp. Unpublish to turn it off.');
  });
  it('asks to pick the number when there is none', () => {
    expect(startSummary({ type: 'whatsapp' }, 'f', 'https://x')).toEqual({ kind: 'none', text: 'once you pick a WhatsApp number' });
    expect(startSummary({ type: 'telegram' }, 'f', 'https://x').text).toBe('once you pick a Telegram bot');
  });
});
