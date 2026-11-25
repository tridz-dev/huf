import { describe, expect, it } from 'vitest';
import { buildRunStory } from './runSteps';

const base = { flow_run_id: 'r', flow_id: 'f', flow_name: 'F', flow_version: 1, mode: 'Normal', trigger_type: 'Manual', hop_count: 0, last_agent_run: null, started_at: '2026-10-29T17:15:00Z', completed_at: null, stale: false, can_mark_failed: false, stale_after_minutes: 15 };
const story = (over: Record<string, unknown>) =>
  buildRunStory({ ...base, waiting: {}, last_error: null, node_labels: { t: 'Tool', c: 'Sub' }, step_meta: { t: { type: 'tool.call', tries: 3 }, c: { type: 'flow.call', flow_name: 'Onboarding' } }, ...over } as never, { titleOf: (id: string) => ({ t: 'Tool', c: 'Sub' } as Record<string, string>)[id] ?? null });

describe('retry words', () => {
  it('a parked retry names the coming try out of the total', () => {
    const s = story({ status: 'Waiting Timer', current_node_id: 't', waiting: { reason: 'retry', resume_at: '2026-10-29T17:20:00', extra: { attempt: 1 } }, context_json: { __node_outputs__: {} } });
    expect(s.steps[0].sentence).toMatch(/^Failed, trying again at .* \(try 2 of 3\)$/);
  });
  it('done after a retry and exhausted', () => {
    const done = story({ status: 'Success', current_node_id: '', context_json: { __node_outputs__: { t: { ok: 1, attempts: 2 } } } });
    expect(done.steps[0].sentence).toBe('Worked on try 2 of 3');
    const failed = story({ status: 'Failed', current_node_id: 't', last_error: 'boom', context_json: { __node_outputs__: { t: { status: 'failed', error: 'boom', attempts: 3 } } } });
    expect(failed.steps[0].phrase).toBe('Failed after 3 tries');
  });
});

describe('sub-flow words', () => {
  it('started, waiting, finished and failed', () => {
    expect(story({ status: 'Success', current_node_id: '', context_json: { __node_outputs__: { c: { flow_id: 'x', run: 'r2' } } } }).steps[0].phrase).toBe('Started Onboarding');
    expect(story({ status: 'Waiting Timer', current_node_id: 'c', waiting: { reason: 'child', extra: { child: 'r2' } }, context_json: { __node_outputs__: {} } }).steps[0].phrase).toBe('Waiting for Onboarding to finish');
    expect(story({ status: 'Success', current_node_id: '', context_json: { __node_outputs__: { c: { answer: 1 } } } }).steps[0].phrase).toBe('Onboarding finished');
    expect(story({ status: 'Failed', current_node_id: 'c', last_error: 'Nope', context_json: { __node_outputs__: {} } }).steps[0].phrase).toBe('Onboarding failed: Nope');
  });
});
