import { describe, expect, it } from 'vitest';
import { FIXTURE_REGISTRY } from './registryFixture';
import { filterSummary, gatewayPhrase, gatewayStopLine, gatewaySubtitle } from './gatewaySummary';
import { channelWord, gatewayDisplayName, gatewaysForKind, isGatewayKindId, NODE_TITLE, pickPrompt } from './gatewayWords';

const gws = FIXTURE_REGISTRY.gateways;

describe('card subtitle', () => {
  it('asks for the channel when none is chosen', () => {
    expect(gatewaySubtitle('whatsapp', {}, gws)).toBe('Pick a WhatsApp number');
    expect(gatewaySubtitle('telegram', { gateway: '' }, gws)).toBe('Pick a Telegram bot');
    expect(gatewaySubtitle('gateway', {}, gws)).toBe('Pick a channel');
  });

  it('names the channel by its label and kind', () => {
    expect(gatewaySubtitle('whatsapp', { gateway: 'Support WhatsApp' }, gws)).toBe('When someone messages Support (WhatsApp)');
    expect(gatewaySubtitle('gateway', { gateway: 'Team Slack' }, gws)).toBe('When someone messages Team chat (Slack)');
    expect(gatewaySubtitle('gateway', { gateway: 'Unknown one' }, null)).toBe('When someone messages Unknown one');
  });

  it('shows the filter instead when there is one', () => {
    expect(gatewaySubtitle('whatsapp', { gateway: 'Support WhatsApp', params: [{ key: 'keywords', value: ['order'] }] }, gws)).toBe("Only messages that contain 'order'");
  });
});

describe('filterSummary', () => {
  it('reads like a sentence', () => {
    expect(filterSummary({ params: [{ key: 'keywords', value: ['order', 'refund'] }] })).toBe("Only messages that contain 'order' or 'refund'");
    expect(filterSummary({ params: [{ key: 'keywords', value: ['a', 'b', 'c', 'd'] }] })).toBe("Only messages that contain 'a', 'b' or 'c' or more");
    expect(filterSummary({ params: [{ key: 'starts_with', value: 'Hi' }] })).toBe("Only messages that start with 'Hi'");
    expect(filterSummary({ params: [{ key: 'commands', value: ['start', '/help'] }] })).toBe('Only /start, /help');
    expect(filterSummary({ params: [{ key: 'message_kinds', value: ['voice'] }] })).toBe('Only voice messages');
    expect(filterSummary({ params: [{ key: 'only_senders', value: ['Asha'] }] })).toBe('Only messages from Asha');
    expect(filterSummary({ params: [{ key: 'has_attachment', value: true }] })).toBe('Only some messages');
  });
  it('is null for the unfiltered trigger and ignores housekeeping options', () => {
    expect(filterSummary({})).toBeNull();
    expect(filterSummary({ params: [{ key: 'max_runs_per_sender_per_hour', value: 5 }, { key: 'ignore_bots', value: false }] })).toBeNull();
  });
});

describe('phrases and words', () => {
  it('list and publish phrases', () => {
    expect(gatewayPhrase('whatsapp', { gateway: 'Support WhatsApp' }, gws)).toBe('someone messages Support on WhatsApp');
    expect(gatewayPhrase('telegram', {}, gws)).toBe('someone messages you on Telegram');
    expect(gatewayPhrase('gateway', {}, gws)).toBe('someone sends a chat message');
    expect(gatewayStopLine({ gateway: 'Support WhatsApp' }, gws)).toBe('Messages to Support will no longer start it.');
    expect(gatewayStopLine({}, gws)).toBe('Chat messages will no longer start it.');
  });
  it('helpers', () => {
    expect(pickPrompt('whatsapp')).toBe('Pick a WhatsApp number');
    expect(gatewaysForKind('whatsapp', gws).map((g) => g.name)).toEqual(['Support WhatsApp']);
    expect(gatewaysForKind('gateway', gws)).toHaveLength(3);
    expect(gatewayDisplayName('Support WhatsApp', gws)).toBe('Support');
    expect(gatewayDisplayName(undefined, gws)).toBe('');
    expect(channelWord('telegram', undefined, null)).toBe('Telegram');
    expect(isGatewayKindId('whatsapp')).toBe(true);
    expect(isGatewayKindId('webhook')).toBe(false);
    expect(NODE_TITLE.telegram).toBe('Telegram message');
  });
});
