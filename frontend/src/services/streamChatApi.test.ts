// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./chatApi', () => ({ newConversation: vi.fn(), sendMessageToConversation: vi.fn(), getAgentRunStatus: vi.fn() }));
vi.mock('@/lib/frappe-sdk', () => ({ call: { post: vi.fn(), get: vi.fn() }, db: { getDocList: vi.fn() } }));
vi.mock('@/components/chat/composer/gatewayRecovery', async (orig) => ({
  ...(await orig<typeof import('@/components/chat/composer/gatewayRecovery')>()),
  recoverRunAfterGateway: vi.fn(),
}));

import { sendMessage } from './streamChatApi';
import { recoverRunAfterGateway } from '@/components/chat/composer/gatewayRecovery';
import { getStreamRunId } from '@/components/chat/composer/activeRun';

const recover = vi.mocked(recoverRunAfterGateway);

function stubFetch(res: Partial<Response>) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res));
}

function sseResponse(frames: unknown[]): Partial<Response> {
  const enc = new TextEncoder();
  const body = new ReadableStream({
    start(c) {
      for (const f of frames) c.enqueue(enc.encode(`data: ${JSON.stringify(f)}\n\n`));
      c.close();
    },
  });
  return { ok: true, status: 200, body } as Partial<Response>;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('sendMessage gateway recovery', () => {
  it.each([502, 503, 504])('polls the run instead of failing at once on %i', async (status) => {
    stubFetch({ ok: false, status });
    recover.mockResolvedValue({
      success: true, queued: false, status: 'Success', response: 'late answer',
      conversation_id: 'C', agent_run_id: 'R', agent_message_id: 'M',
    });
    const res = await sendMessage({ agent: 'a', message: 'hi', conversationId: 'C' }, { useStreaming: true });
    expect(recover).toHaveBeenCalledWith(expect.objectContaining({ conversationId: 'C', runId: null }));
    expect(res.message).toMatchObject({ success: true, response: 'late answer', agent_run_id: 'R' });
    expect(fetch).toHaveBeenCalledTimes(1); // no automatic re-send
  });

  it('reports a failed run with its real error', async () => {
    stubFetch({ ok: false, status: 504 });
    recover.mockResolvedValue({ success: false, queued: false, status: 'Failed', error: 'tool crashed', agent_run_id: 'R' });
    const res = await sendMessage({ agent: 'a', message: 'hi', conversationId: 'C' }, { useStreaming: true });
    expect(res.message).toMatchObject({ success: false, error: 'tool crashed' });
  });

  it('returns a queued ack when the run is still open at the deadline', async () => {
    stubFetch({ ok: false, status: 504 });
    recover.mockResolvedValue({ success: true, queued: true, status: 'Started', conversation_id: 'C', agent_run_id: 'R' });
    const res = await sendMessage({ agent: 'a', message: 'hi', conversationId: 'C' }, { useStreaming: true });
    expect(res.message).toMatchObject({ queued: true, agent_run_id: 'R' });
  });

  it('does not recover from other statuses', async () => {
    stubFetch({ ok: false, status: 500 });
    await expect(
      sendMessage({ agent: 'a', message: 'hi', conversationId: 'C' }, { useStreaming: true })
    ).rejects.toThrow('Request failed: 500');
    expect(recover).not.toHaveBeenCalled();
  });
});

describe('run_started frame', () => {
  it('records the run id while streaming and clears it afterwards', async () => {
    let seen: string | null = null;
    stubFetch(
      sseResponse([
        { type: 'run_started', agent_run_id: 'R9', conversation_id: 'C' },
        { type: 'delta', full_response: 'x' },
        { type: 'complete', success: true, response: 'x', conversation_id: 'C', agent_run_id: 'R9' },
      ])
    );
    await sendMessage(
      { agent: 'a', message: 'hi', conversationId: 'C' },
      { useStreaming: true, onDelta: () => { seen = getStreamRunId(); } }
    );
    expect(seen).toBe('R9');
    expect(getStreamRunId()).toBeNull();
  });
});
