import type { WebhookTriggerConfig } from '../types/flow.types';

/** Random webhook key: a UUID where available, otherwise 16 random bytes as hex. */
export function generateWebhookKey(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Default config for a newly added webhook trigger. The key lives on `auth`,
 * the same field RightSidebar reads and writes. Writing it under another name
 * made it vanish when the node was reselected.
 */
export function createWebhookTriggerDefaults(origin: string, newKey: () => string = generateWebhookKey): WebhookTriggerConfig {
  return {
    type: 'webhook',
    url: `${origin}/api/method/huf.ai.flow.api.flow_webhook`,
    auth: newKey(),
    method: 'POST',
  };
}
