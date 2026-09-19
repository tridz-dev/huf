import { describe, expect, it } from 'vitest';
import { getGatewayWebhookUrl } from './gatewayWebhook';

const ORIGIN = 'https://huf.example.com';

describe('getGatewayWebhookUrl', () => {
  it('routes Slack through slack_events.handle_slack_event', () => {
    expect(getGatewayWebhookUrl('Support Slack', 'Slack', ORIGIN)).toBe(
      `${ORIGIN}/api/method/huf.ai.gateways.slack_events.handle_slack_event?gateway_name=Support%20Slack`,
    );
  });

  it('routes every other provider through the generic gateway_webhook handler', () => {
    const providers = ['WhatsApp', 'Messenger', 'Instagram', 'Telegram', 'Email', 'Google Chat', 'Microsoft Teams'];
    for (const provider of providers) {
      expect(getGatewayWebhookUrl('gw-1', provider, ORIGIN)).toBe(
        `${ORIGIN}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=gw-1`,
      );
    }
  });

  it('falls back to the generic handler when provider is unknown/undefined', () => {
    expect(getGatewayWebhookUrl('gw-1', undefined, ORIGIN)).toBe(
      `${ORIGIN}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=gw-1`,
    );
  });

  it('URL-encodes the gateway name', () => {
    expect(getGatewayWebhookUrl('My Gateway/Name', 'WhatsApp', ORIGIN)).toContain(
      encodeURIComponent('My Gateway/Name'),
    );
  });
});
