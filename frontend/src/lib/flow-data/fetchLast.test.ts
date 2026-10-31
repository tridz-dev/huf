import { beforeEach, describe, expect, it, vi } from 'vitest';

const webhook = vi.fn();
const chat = vi.fn();
vi.mock('@/services/flow/triggerApi', () => ({ getLastWebhookRequest: (...a: unknown[]) => webhook(...a) }));
vi.mock('@/services/flow/gateway/samplesApi', () => ({ getLastGatewayMessage: (...a: unknown[]) => chat(...a) }));

import { fetchLastSample } from './fetchLast';
import type { PickerStep } from './model';

const step = (type: string) => ({ id: 't1', node: { data: { triggerConfig: { type } } } }) as unknown as PickerStep;

describe('fetchLastSample', () => {
  beforeEach(() => { webhook.mockReset(); chat.mockReset(); });
  it('sends a chat trigger to the messages service, never the webhook endpoint', async () => {
    chat.mockResolvedValue({ found: true, sample: { text: 'hi' }, real: true });
    const out = await fetchLastSample('f1', step('whatsapp'));
    expect(chat).toHaveBeenCalledWith('f1', 't1');
    expect(webhook).not.toHaveBeenCalled();
    expect(out).toMatchObject({ sample: { text: 'hi' }, noun: 'message' });
  });
  it('keeps the webhook on its own endpoint', async () => {
    webhook.mockResolvedValue({ found: false, sample: null });
    const out = await fetchLastSample('f1', step('webhook'));
    expect(chat).not.toHaveBeenCalled();
    expect(out.sample).toBeNull();
    expect(out.notice).toContain('webhook');
  });
});
