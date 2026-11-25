import { describe, expect, it } from 'vitest';
import { isResumeWait, runStatusPill } from './runStatus';
import { runHeadline } from './headline';
import { buildRunStory } from './runSteps';

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

describe('step words for the new steps', () => {
  const base = { flow_run_id: 'r', flow_id: 'f', flow_name: 'F', flow_version: 1, mode: 'Normal', trigger_type: 'Manual', hop_count: 0, last_agent_run: null, started_at: '2026-10-29T17:15:00Z', completed_at: null, stale: false, can_mark_failed: false, stale_after_minutes: 15 };
  const story = (over: Record<string, unknown>) =>
    buildRunStory({ ...base, waiting: {}, last_error: null, node_labels: { a: 'Rules', w: 'Wait', s: 'Stop' }, step_meta: { a: { type: 'router.decision' }, w: { type: 'wait' }, s: { type: 'stop' } }, ...over } as never, { titleOf: (id: string) => ({ a: 'Rules', w: 'Wait', s: 'Stop' } as Record<string, string>)[id] ?? null });

  it('a switch says which rule matched, or that none did', () => {
    const matched = story({ status: 'Success', current_node_id: '', context_json: { __node_outputs__: { a: { case: 'Big', node_id: 'x' } } } });
    expect(matched.steps[0].sentence).toBe('Matched rule "Big"');
    const none = story({ status: 'Success', current_node_id: '', context_json: { __node_outputs__: { a: { case: null, node_id: 'x' } } } });
    expect(none.steps[0].sentence).toBe('No rule matched, went the default way');
  });

  it('a finished wait says how it ended', () => {
    const out = (reason: string) => story({ status: 'Success', current_node_id: '', context_json: { __node_outputs__: { w: { waited_until: null, reason } } } }).steps[0].sentence;
    expect(out('reply')).toBe('Continued by a reply');
    expect(out('continued')).toBe('Continued by someone');
    expect(out('timeout')).toBe('Gave up waiting');
  });

  it('a parked wait says what it waits for', () => {
    const parked = (extra: Record<string, unknown>) => story({ status: 'Waiting Timer', current_node_id: 'w', waiting: { reason: 'wait', extra }, context_json: { __node_outputs__: {} } }).steps[0].sentence;
    expect(parked({ mode: 'resume', wait_for: 'token' })).toBe('Waiting for someone to continue it');
    expect(parked({ mode: 'resume', wait_for: 'member_reply' })).toBe('Waiting for the person to reply');
  });

  it('a stop names its message', () => {
    const failed = story({ status: 'Failed', current_node_id: 's', last_error: 'Order blocked', context_json: { __node_outputs__: {} } });
    expect(failed.steps[0].phrase).toBe('Stopped the flow: Order blocked');
  });
});
