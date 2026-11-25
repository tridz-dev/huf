import { describe, expect, it } from 'vitest';
import { isResumeWait, runStatusPill } from './runStatus';
import { runHeadline } from './headline';

const run = (status: string, mode?: string) => ({ status, waiting: mode ? { extra: { mode } } : {} }) as never;

describe('a run waiting on "until someone continues it"', () => {
  it('says so in the pill and the headline, and a timed wait keeps the timer words', () => {
    expect(isResumeWait(run('Waiting Timer', 'resume'))).toBe(true);
    expect(isResumeWait(run('Waiting Timer', 'duration'))).toBe(false);
    expect(isResumeWait(run('Running', 'resume'))).toBe(false);
    expect(runStatusPill({ status: 'Waiting Timer', resumeWait: true })).toEqual({ kind: 'waiting_timer', label: 'Waiting to be continued' });
    expect(runStatusPill({ status: 'Waiting Timer' })).toEqual({ kind: 'waiting_timer' });
    expect(runHeadline(run('Waiting Timer', 'resume')).headline).toBe('Waiting for someone to continue it');
    expect(runHeadline(run('Waiting Timer', 'duration')).headline).toBe('Waiting for a timer');
  });
});
