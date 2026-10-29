import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
vi.mock('@/lib/frappe-sdk', () => ({ call: { post: (...a: unknown[]) => post(...a) }, db: {} }));

describe('listSlackChannels', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    post.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it('gives up with a readable error instead of waiting forever', async () => {
    post.mockReturnValue(new Promise(() => undefined));
    const { listSlackChannels, SLACK_CHANNELS_TIMEOUT_MS } = await import('./integrationApi');
    const pending = listSlackChannels('slack-0018');
    const assertion = expect(pending).rejects.toThrow(/taking too long/);
    await vi.advanceTimersByTimeAsync(SLACK_CHANNELS_TIMEOUT_MS + 10);
    await assertion;
  });

  it('returns the answer when Slack replies in time', async () => {
    post.mockResolvedValue({ message: { status: 'Connected', channels: [] } });
    const { listSlackChannels } = await import('./integrationApi');
    await expect(listSlackChannels('x')).resolves.toEqual({ status: 'Connected', channels: [] });
  });
});
