import { describe, it, expect } from 'vitest';
import { createWebhookTriggerDefaults } from './flowWebhookConfig';

describe('createWebhookTriggerDefaults', () => {
  it('stores the generated key on `auth`, not `apiKey`', () => {
    const config = createWebhookTriggerDefaults('https://huf.test', () => 'key-123');
    expect(config.auth).toBe('key-123');
    expect(config).not.toHaveProperty('apiKey');
  });

  it('builds the webhook URL from the origin and sets POST', () => {
    const config = createWebhookTriggerDefaults('https://huf.test', () => 'k');
    expect(config).toEqual({
      type: 'webhook',
      url: 'https://huf.test/api/method/huf.ai.flow.api.flow_webhook',
      auth: 'k',
      method: 'POST',
    });
  });
});
