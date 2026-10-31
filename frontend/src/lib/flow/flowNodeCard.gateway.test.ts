// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { triggerSubtitle } from './flowNodeCard';
import { triggerStepFields } from './flowLabels';
import { FIXTURE_REGISTRY } from '../flow-gateway/registryFixture';
import { sensitiveFlowFeatures, publishBlockedReason } from './flowPublishGuard';
import { triggerOptions } from '../../data/triggers';
import { paletteIcon } from '../../components/nodes/nodeIcons';
import type { FlowNode } from '../../types/flow.types';

const gws = FIXTURE_REGISTRY.gateways;

describe('chat trigger card', () => {
  it('reads "When someone messages Support (WhatsApp)", or the filter, or asks for the number', () => {
    expect(triggerSubtitle({ type: 'whatsapp', gateway: 'Support WhatsApp' }, gws)).toBe('When someone messages Support (WhatsApp)');
    expect(triggerSubtitle({ type: 'whatsapp', gateway: 'Support WhatsApp', params: [{ key: 'keywords', value: ['order'] }] }, gws)).toBe('Support · Contains "order"');
    expect(triggerSubtitle({ type: 'whatsapp' })).toBe('Pick a WhatsApp number');
  });

  it('other triggers keep their subtitles', () => {
    expect(triggerSubtitle({ type: 'webhook' })).toBe('Runs on a web request');
    expect(triggerSubtitle(undefined)).toBe('Choose what starts this flow');
  });

  it('titles, icons and the set-up flag follow the trigger table', () => {
    expect(triggerStepFields({ type: 'whatsapp' })).toMatchObject({ label: 'WhatsApp message', icon: 'MessageCircle', configured: false });
    expect(triggerStepFields({ type: 'telegram', gateway: 'Sales Bot' })).toMatchObject({ label: 'Telegram message', icon: 'Send', configured: true });
    expect(triggerStepFields({ type: 'gateway' })).toMatchObject({ label: 'Chat message', icon: 'MessageSquare' });
    expect(triggerStepFields({ type: 'webhook' })).toMatchObject({ icon: 'Webhook', configured: true });
  });

  it('every palette card has an icon that exists', () => {
    for (const t of triggerOptions) expect(paletteIcon(t.icon).displayName ?? paletteIcon(t.icon)).toBeTruthy();
    expect(triggerOptions.map((t) => t.name)).toEqual(expect.arrayContaining(['A chat message', 'A WhatsApp message', 'A Telegram message']));
  });
});

describe('publish guard', () => {
  const chat = { id: 'n', data: { label: 'n', nodeType: 'trigger', triggerConfig: { type: 'telegram', gateway: 'x' } } } as unknown as FlowNode;
  it('a chat trigger is sensitive and named once', () => {
    expect(sensitiveFlowFeatures([chat, chat])).toEqual(['a chat-message trigger']);
    expect(publishBlockedReason([chat], false)).toContain('a chat-message trigger');
    expect(publishBlockedReason([chat], true)).toBeNull();
  });
});
