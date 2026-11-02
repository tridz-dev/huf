import type { StepTestPending, StepTestResult } from '@/services/flow/stepTestApi';

/** One second between asks, and up to 35 seconds in all (the server stops a step at 30 seconds). */
export const STEP_POLL_INTERVAL_MS = 1000;
export const STEP_POLL_MAX_MS = 35000;
export const STEP_POLL_BUSY_MESSAGE = 'The background worker is busy: try again';

export interface PollOptions {
  fetchResult: (token: string) => Promise<StepTestResult | StepTestPending>;
  /** True once the person left (unmounted, changed step): polling stops and nothing is stored. */
  isCancelled: () => boolean;
  intervalMs?: number;
  maxMs?: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

const realSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Waits for a queued step test. Returns the result, `null` when cancelled, and throws the plain
 * "background worker is busy" sentence when 35 seconds pass without an answer.
 */
export async function pollStepTest(first: StepTestPending, options: PollOptions): Promise<StepTestResult | null> {
  const interval = options.intervalMs ?? STEP_POLL_INTERVAL_MS;
  const maxMs = options.maxMs ?? STEP_POLL_MAX_MS;
  const sleep = options.sleep ?? realSleep;
  const now = options.now ?? Date.now;
  const started = now();
  while (now() - started < maxMs) {
    await sleep(Math.min(first.poll_after_ms || interval, interval));
    if (options.isCancelled()) return null;
    const next = await options.fetchResult(first.token);
    if (options.isCancelled()) return null;
    if (next.status !== 'running') return next;
  }
  throw new Error(STEP_POLL_BUSY_MESSAGE);
}
