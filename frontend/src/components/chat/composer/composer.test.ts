import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { post: vi.fn(), get: vi.fn() }, db: { getDocList: vi.fn() } }));
vi.mock('@/services/chatApi', () => ({ getAgentRunStatus: vi.fn() }));

import { findPendingRunId } from './activeRun';
import { recoverRunAfterGateway } from './gatewayRecovery';
import { applyStopOutcome, cancelAndAwaitRun, markStopping } from './stopRun';
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

const stopDeps = { sleep: async () => undefined, now: () => 0, pollMs: 1, totalTimeoutMs: 1000 };
const requested = { run_id: 'R', status: 'Started' as const, cancel_requested: true };

describe('stop', () => {
  it('shows stopping, not cancelled, for a run the server has only been asked to cancel', () => {
    const [queued] = markStopping([msg({ key: 'run1', runStatus: 'Started' })], 'run1', false);
    expect(queued).toMatchObject({ stopping: true, runStatus: 'Started' });
    expect(queued.error).toBeUndefined();
    const [streaming] = markStopping([msg({ key: 'assistant-1' })], 'run2', true);
    expect(streaming).toMatchObject({ stopping: true, agentRunId: 'run2' });
    expect(streaming.error).toBeUndefined();
  });

  it('polls until the run is terminal before reporting it cancelled', async () => {
    const getStatus = vi
      .fn()
      .mockResolvedValueOnce({ status: 'Started' })
      .mockRejectedValueOnce(new Error('blip'))
      .mockResolvedValueOnce({ status: 'Failed', error: 'Client disconnected' });
    const out = await cancelAndAwaitRun('R', { ...stopDeps, cancel: async () => requested, getStatus });
    expect(getStatus).toHaveBeenCalledTimes(3);
    expect(out).toEqual({ status: 'Failed', error: 'Cancelled by user' });
  });

  it('reports nothing for a run still open at the deadline', async () => {
    let t = 0;
    const out = await cancelAndAwaitRun('R', {
      ...stopDeps,
      now: () => t,
      sleep: async () => { t += 600; },
      cancel: async () => requested,
      getStatus: vi.fn().mockResolvedValue({ status: 'Started' }),
    });
    expect(out).toBeNull();
    const [m] = applyStopOutcome([msg({ key: 'R', runStatus: 'Started', stopping: true })], 'R', out);
    expect(m).toMatchObject({ stopping: false, runStatus: 'Started' });
  });

  it('shows the real reply of a run that finished before the stop', () => {
    const [m] = applyStopOutcome([msg({ key: 'assistant-1', agentRunId: 'R', stopping: true })], 'R', {
      status: 'Success',
      response: 'done',
    });
    expect(m).toMatchObject({ runStatus: 'Success', stopping: false });
    expect(m.versions[0].content).toBe('done');
  });
});

const fast = { sleep: async () => undefined, pollMs: 1 };

describe('recoverRunAfterGateway', () => {
  it('returns the real result of a run that finished after the timeout', async () => {
    const getStatus = vi
      .fn()
      .mockResolvedValueOnce({ status: 'Started', agent_run_id: 'R' })
      .mockResolvedValueOnce({ status: 'Success', response: 'done', agent_run_id: 'R', agent_message_id: 'M' });
    const out = await recoverRunAfterGateway({ runId: 'R', startedAt: Date.now() }, { ...fast, getStatus });
    expect(out).toMatchObject({ success: true, queued: false, response: 'done', agent_message_id: 'M' });
  });

  it('surfaces a failed run', async () => {
    const getStatus = vi.fn().mockResolvedValue({ status: 'Failed', error: 'boom', agent_run_id: 'R' });
    const out = await recoverRunAfterGateway({ runId: 'R', startedAt: Date.now() }, { ...fast, getStatus });
    expect(out).toMatchObject({ success: false, error: 'boom' });
  });

  it('finds the run by conversation when the id is unknown', async () => {
    const findRun = vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce('R2');
    const getStatus = vi.fn().mockResolvedValue({ status: 'Success', response: 'ok', agent_run_id: 'R2' });
    const out = await recoverRunAfterGateway({ conversationId: 'C', startedAt: Date.now() }, { ...fast, findRun, getStatus });
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

  it('recovers a brand-new chat by the client key, before any conversation is known', async () => {
    const findByKey = vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce('R3');
    const getStatus = vi.fn().mockResolvedValue({ status: 'Success', response: 'ok', conversation_id: 'NEW' });
    const out = await recoverRunAfterGateway({ clientKey: 'k1', startedAt: Date.now() }, { ...fast, findByKey, getStatus });
    expect(findByKey).toHaveBeenCalledWith('k1');
    expect(out).toMatchObject({ success: true, agent_run_id: 'R3', conversation_id: 'NEW', response: 'ok' });
  });

  it('fails clearly when there is neither a client key nor a conversation to search', async () => {
    await expect(recoverRunAfterGateway({ startedAt: Date.now() }, fast)).rejects.toThrow(/timed out/);
  });
});
