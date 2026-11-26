import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { post: vi.fn(), get: vi.fn() }, db: { getDocList: vi.fn() } }));
vi.mock('@/services/chatApi', () => ({ getAgentRunStatus: vi.fn() }));

import { findPendingRunId } from './activeRun';
import { recoverRunAfterGateway } from './gatewayRecovery';
import { markCancelled } from './useRunStop';
import type { MessageType } from '../types';

const msg = (over: Partial<MessageType>): MessageType =>
  ({ key: 'k', from: 'assistant', versions: [{ id: 'k', content: '' }], ...over }) as MessageType;

describe('findPendingRunId', () => {
  it('returns the newest queued/started run and ignores finished ones', () => {
    const messages = [msg({ key: 'a', runStatus: 'Queued' }), msg({ key: 'b', runStatus: 'Started' }), msg({ key: 'c', runStatus: 'Success' })];
    expect(findPendingRunId(messages)).toBe('b');
    expect(findPendingRunId([msg({ key: 'c', runStatus: 'Failed' })])).toBeNull();
  });
});

describe('markCancelled', () => {
  it('marks a queued run bubble as cancelled', () => {
    const out = markCancelled([msg({ key: 'run1', runStatus: 'Queued' })], 'run1', false);
    expect(out[0].runStatus).toBe('Failed');
    expect(out[0].error).toBe('Cancelled by user');
  });
  it('marks the in-flight streaming bubble (no runStatus) as cancelled', () => {
    const out = markCancelled([msg({ key: 'assistant-1' })], 'run2', true);
    expect(out[0].error).toBe('Cancelled by user');
  });
});

const fast = { sleep: async () => undefined, pollMs: 1 };

describe('recoverRunAfterGateway', () => {
  it('returns the real result of a run that finished after the timeout', async () => {
    const getStatus = vi
      .fn()
      .mockResolvedValueOnce({ status: 'Started', agent_run_id: 'R' })
      .mockResolvedValueOnce({ status: 'Success', response: 'done', agent_run_id: 'R', agent_message_id: 'M' });
    const out = await recoverRunAfterGateway({ runId: 'R', startedAt: 0 }, { ...fast, getStatus });
    expect(out).toMatchObject({ success: true, queued: false, response: 'done', agent_message_id: 'M' });
  });

  it('surfaces a failed run', async () => {
    const getStatus = vi.fn().mockResolvedValue({ status: 'Failed', error: 'boom', agent_run_id: 'R' });
    const out = await recoverRunAfterGateway({ runId: 'R', startedAt: 0 }, { ...fast, getStatus });
    expect(out).toMatchObject({ success: false, error: 'boom' });
  });

  it('finds the run by conversation when the id is unknown', async () => {
    const findRun = vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce('R2');
    const getStatus = vi.fn().mockResolvedValue({ status: 'Success', response: 'ok', agent_run_id: 'R2' });
    const out = await recoverRunAfterGateway({ conversationId: 'C', startedAt: 0 }, { ...fast, findRun, getStatus });
    expect(out.agent_run_id).toBe('R2');
    expect(getStatus).toHaveBeenCalledWith('R2');
  });

  it('is bounded: hands a still-open run to the run poller at the deadline', async () => {
    let t = 0;
    const getStatus = vi.fn().mockResolvedValue({ status: 'Started', agent_run_id: 'R' });
    const out = await recoverRunAfterGateway(
      { runId: 'R', startedAt: 0 },
      { ...fast, getStatus, now: () => t, sleep: async () => { t += 50_000; }, totalTimeoutMs: 120_000 }
    );
    expect(out).toMatchObject({ queued: true, status: 'Started', agent_run_id: 'R' });
  });

  it('gives up with a clear error when no run exists, without re-sending', async () => {
    let t = 0;
    const findRun = vi.fn().mockResolvedValue(null);
    await expect(
      recoverRunAfterGateway(
        { conversationId: 'C', startedAt: 0 },
        { findRun, getStatus: vi.fn(), now: () => t, sleep: async () => { t += 20_000; }, findTimeoutMs: 30_000 }
      )
    ).rejects.toThrow(/no run was found/);
  });

  it('cannot look up a run for a brand-new conversation', async () => {
    await expect(recoverRunAfterGateway({ startedAt: 0 }, fast)).rejects.toThrow(/timed out/);
  });
});
