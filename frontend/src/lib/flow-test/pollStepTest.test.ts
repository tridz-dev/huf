import { describe, expect, it, vi } from 'vitest';
import type { StepTestPending, StepTestResult } from '@/services/flow/stepTestApi';
import { pollStepTest, STEP_POLL_BUSY_MESSAGE, STEP_POLL_INTERVAL_MS, STEP_POLL_MAX_MS } from './pollStepTest';

const pending: StepTestPending = { status: 'running', token: 'a'.repeat(32), poll_after_ms: 1000, wait_up_to_s: 35 };
const done = { status: 'success', output: 'Hi' } as StepTestResult;

function clock() {
  let t = 0;
  return { now: () => t, sleep: vi.fn(async (ms: number) => { t += ms; }) };
}

describe('pollStepTest', () => {
  it('asks once a second until the answer is ready', async () => {
    const c = clock();
    const fetchResult = vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(pending).mockResolvedValueOnce(done);
    const out = await pollStepTest(pending, { fetchResult, isCancelled: () => false, ...c });
    expect(out).toBe(done);
    expect(fetchResult).toHaveBeenCalledTimes(3);
    expect(c.sleep.mock.calls.every(([ms]) => ms === STEP_POLL_INTERVAL_MS)).toBe(true);
  });

  it('gives up after 35 seconds with a plain sentence', async () => {
    const c = clock();
    const fetchResult = vi.fn().mockResolvedValue(pending);
    await expect(pollStepTest(pending, { fetchResult, isCancelled: () => false, ...c })).rejects.toThrow(STEP_POLL_BUSY_MESSAGE);
    expect(STEP_POLL_BUSY_MESSAGE).toBe('The background worker is busy: try again');
    expect(fetchResult).toHaveBeenCalledTimes(STEP_POLL_MAX_MS / STEP_POLL_INTERVAL_MS);
  });

  it('stops asking when cancelled (the person left) and returns nothing', async () => {
    const c = clock();
    let cancelled = false;
    const fetchResult = vi.fn(async () => {
      cancelled = true;
      return pending;
    });
    expect(await pollStepTest(pending, { fetchResult, isCancelled: () => cancelled, ...c })).toBeNull();
    expect(fetchResult).toHaveBeenCalledTimes(1);
  });

  it('does not ask at all when cancelled before the first wait ends', async () => {
    const c = clock();
    const fetchResult = vi.fn();
    expect(await pollStepTest(pending, { fetchResult, isCancelled: () => true, ...c })).toBeNull();
    expect(fetchResult).not.toHaveBeenCalled();
  });

  it('passes a failed answer through as an answer', async () => {
    const c = clock();
    const failed = { status: 'failed', error: 'The test could not start because the background worker is busy. Try again in a moment.' } as StepTestResult;
    const out = await pollStepTest(pending, { fetchResult: vi.fn().mockResolvedValue(failed), isCancelled: () => false, ...c });
    expect(out).toBe(failed);
  });
});
