import { describe, expect, it } from 'vitest';
import type { FlowRunDetail } from '@/services/flowApi';
import { formatDuration, runDuration, spokenDuration } from './time';
import { plainRunError } from './runErrors';
import { runStatusPill, stoppedByPerson } from './runStatus';
import { buildRunStory } from './runSteps';
import { runHeadline } from './headline';
import { overlayFromRun } from './overlay';

const run = (over: Partial<FlowRunDetail>): FlowRunDetail => ({
  flow_run_id: 'r1', flow_id: 'f', flow_name: 'Flow', flow_version: 1, mode: 'Normal', status: 'Success', trigger_type: 'Manual',
  current_node_id: '', hop_count: 0, context_json: {}, waiting: {}, node_labels: {}, last_error: null, last_agent_run: null,
  started_at: '2026-10-29T17:15:00Z', completed_at: '2026-10-29T17:15:06Z', stale: false, can_mark_failed: false, stale_after_minutes: 15, ...over,
});
const titleOf = (run0: FlowRunDetail) => (id: string) => run0.node_labels[id] ?? null;

describe('durations', () => {
  it('reads like a person would say it', () => {
    expect(formatDuration(0)).toBe('Under 1 s');
    expect(formatDuration(6_000)).toBe('6 s');
    expect(formatDuration(125_000)).toBe('2 min 5 s');
    expect(formatDuration(121 * 60_000 + 4_000)).toBe('2 h 1 min');
    expect(formatDuration(3 * 3_600_000)).toBe('3 h');
    expect(formatDuration(26 * 3_600_000)).toBe('1 d 2 h');
    expect(formatDuration(-1)).toBe('');
  });
  it('finds the time between two server times', () => {
    expect(runDuration('2026-10-29T17:15:00Z', '2026-10-29T17:15:06Z')).toBe('6 s');
    expect(runDuration('2026-10-29T17:15:00Z', null)).toBe('');
  });
  it('speaks long waits in whole units', () => {
    expect(spokenDuration(2 * 3_600_000 + 60_000)).toBe('2 hours');
    expect(spokenDuration(60_000)).toBe('1 minute');
    expect(spokenDuration(30_000)).toBe('a moment');
    expect(spokenDuration(49 * 3_600_000)).toBe('2 days');
  });
});

describe('plainRunError', () => {
  it('drops the engine wrapper, the step lead-in and python names', () => {
    expect(plainRunError("Node 'n1' of type 'tool.call' failed and declares no on_error successor: Fetch page failed: x broke", 'Fetch page')).toBe('X broke');
    expect(plainRunError("PermissionError: absolute path '/etc/passwd' is outside the sandbox workspace")).toMatch(/^The code tried to open a file it is not allowed to use \(\/etc\/passwd\)/);
    expect(plainRunError("ImportError: Import of module 'socket' is not permitted by execution profile policy")).toMatch(/^The code tried to use "socket"/);
    expect(plainRunError('state.set: another run was saving the same key at that moment. Run it again.')).toBe('Another run was saving the same value at that moment. Run it again.');
    expect(plainRunError('Execution approval rejected by maria@example.com.')).toBe('maria@example.com did not approve running this code.');
  });
  it('drops the call to action the button now carries', () => {
    expect(plainRunError('Google Sheets is not connected. Connect it in Integrations.')).toBe('Google Sheets is not connected.');
  });
});

describe('statuses', () => {
  it('maps stored statuses into the one status set', () => {
    expect(runStatusPill({ status: 'Success' }).kind).toBe('finished');
    expect(runStatusPill({ status: 'Failed' }).kind).toBe('failed');
    expect(runStatusPill({ status: 'Running', stale: true }).kind).toBe('stuck');
    expect(runStatusPill({ status: 'Waiting Code' }).kind).toBe('waiting_review');
    expect(runStatusPill({ status: 'Waiting User' }).label).toBe('Waiting for your reply');
  });
  it('tells a person-ended run from a failure', () => {
    expect(stoppedByPerson('Marked as failed by Administrator: the run was stuck in Running.')?.by).toBe('Administrator');
    expect(stoppedByPerson('Cancelled by ana@example.com before it started.')?.by).toBe('ana@example.com');
    expect(stoppedByPerson('Fetch page failed: boom')).toBeNull();
  });
});

describe('buildRunStory', () => {
  it('groups loop body steps under their loop and counts each card once', () => {
    const r = run({
      status: 'Success', current_node_id: 'wrap',
      context_json: { items: ['a', 'b', 'c'], __node_outputs__: { t: { items: ['a', 'b', 'c'] }, shout: 'C', loop: { result: ['A', 'B', 'C'], output: ['A', 'B', 'C'], skipped: [] }, wrap: 'x' } },
      node_labels: { t: 'Webhook', loop: 'Each name', shout: 'Shout item', wrap: 'Wrap up' },
      step_meta: { t: { type: 'trigger.webhook' }, loop: { type: 'foreach', body: ['shout'] }, shout: { type: 'transform' }, wrap: { type: 'transform' } },
    });
    const story = buildRunStory(r, { titleOf: titleOf(r) });
    expect(story.steps.map((s) => s.id)).toEqual(['t', 'loop', 'wrap']);
    const loop = story.steps[1];
    expect(loop.iterations?.count).toBe(3);
    expect(loop.children?.map((c) => c.id)).toEqual(['shout']);
    expect(story.stepCount).toBe(4);
    expect(story.steps[0].phrase).toBe('Received a webhook');
    expect(story.steps[0].receivedData).toEqual({ items: ['a', 'b', 'c'] });
  });

  it('keeps a running loop first even before it has a result', () => {
    const r = run({
      status: 'Running', current_node_id: 'loop',
      context_json: { __node_outputs__: { t: {}, shout: 'A' } },
      node_labels: { t: 'Webhook', loop: 'Each name', shout: 'Shout item' },
      step_meta: { t: { type: 'trigger.webhook' }, loop: { type: 'foreach', body: ['shout'] }, shout: { type: 'transform' } },
    });
    const story = buildRunStory(r, { titleOf: titleOf(r) });
    expect(story.steps.map((s) => s.id)).toEqual(['t', 'loop']);
    expect(story.steps[1].children?.map((c) => c.id)).toEqual(['shout']);
  });

  it('tells an approval in one sentence with no repeated data', () => {
    const r = run({
      status: 'Success', current_node_id: 'end', outcome: { label: 'Rejected', tone: 'bad' },
      context_json: { amount: 42, __node_outputs__: { t: { amount: 42 }, h: { decision: 'rejected', comment: null, decided_by: 'Administrator', decided_at: '2026-10-29T17:15:54Z' }, end: 'rejected' } },
      node_labels: { t: 'Webhook', h: 'Human in Loop', end: 'Rejected' },
      step_meta: { t: { type: 'trigger.webhook' }, h: { type: 'human.approval' }, end: { type: 'output' } },
    });
    const [, approval, end] = buildRunStory(r, { titleOf: titleOf(r) }).steps;
    expect(approval.phrase).toBe('Waited for approval');
    expect(approval.sentence).toMatch(/^Rejected by Administrator, /);
    expect(approval.hideOutput).toBe(true);
    expect(approval.comment).toBeUndefined();
    expect(end.phrase).toBe('Ended');
    expect(end.sentence).toBeUndefined(); // the step is already titled Rejected
    expect(end.hideOutput).toBe(true);
  });

  it('shows the waiting step and who it waits for', () => {
    const r = run({
      status: 'Waiting Approval', current_node_id: 'h', completed_at: null,
      waiting: { type: 'approval', approver_type: 'role', approver_role: 'System Manager' },
      context_json: { a: 1, __node_outputs__: { t: { a: 1 } } },
      node_labels: { t: 'Webhook', h: 'Wait for approval' },
      step_meta: { t: { type: 'trigger.webhook' }, h: { type: 'human.approval' } },
    });
    const last = buildRunStory(r, { titleOf: titleOf(r) }).steps.at(-1)!;
    expect(last.status).toBe('waiting');
    expect(last.phrase).toBe('Waiting for approval');
    expect(last.sentence).toBe('Waiting for someone with the System Manager role');
  });

  it('gives a failed run exactly one reason, in plain words', () => {
    const r = run({
      status: 'Failed', current_node_id: 'f', last_error: "Node 'f' of type 'tool.call' failed and declares no on_error successor: Fetch page failed: Requests to private/internal addresses are not allowed",
      context_json: { __node_outputs__: { t: {}, f: { error: 'Requests to private/internal addresses are not allowed', status: 'failed' } } },
      node_labels: { t: 'Webhook', f: 'Fetch page' }, step_meta: { t: { type: 'trigger.webhook' }, f: { type: 'tool.call' } },
    });
    const story = buildRunStory(r, { titleOf: titleOf(r) });
    const failed = story.steps.filter((s) => s.status === 'failed');
    expect(failed).toHaveLength(1);
    expect(failed[0].reason).toMatch(/^That address is on a private network/);
    expect(failed[0].output).toBeUndefined();
  });

  it('shows a run ended by a person as stopped, not as an error', () => {
    const r = run({
      status: 'Failed', current_node_id: 'slow', last_error: 'Marked as failed by Administrator: the run was stuck in Running.',
      context_json: {}, node_labels: { slow: 'Slow step' }, step_meta: { slow: { type: 'tool.call' } },
    });
    const [s] = buildRunStory(r, { titleOf: titleOf(r) }).steps;
    expect(s.status).toBe('stopped');
    expect(s.reason).toMatch(/^Stopped by Administrator\./);
    const mine = buildRunStory(r, { titleOf: titleOf(r), currentUser: 'Administrator' }).steps[0];
    expect(mine.reason).toMatch(/^Stopped by you\./);
    expect(runHeadline(r, Date.now(), 'Administrator').headline).toBe('Stopped by you');
  });
});

describe('failed steps', () => {
  it('keep their data behind Raw and say the end outcome when the title does not', () => {
    const r = run({
      status: 'Success', current_node_id: 'end', outcome: { label: 'Order shipped', tone: 'good' },
      context_json: { __node_outputs__: { end: 'done' } }, node_labels: { end: 'Finish' }, step_meta: { end: { type: 'output' } },
    });
    expect(buildRunStory(r, { titleOf: titleOf(r) }).steps[0].sentence).toBe('Order shipped');
    const f = run({
      status: 'Failed', current_node_id: 'h', last_error: 'HTTP 404',
      context_json: { __node_outputs__: { h: { error: 'HTTP 404', status_code: 404, body: 'x' } } }, node_labels: { h: 'HTTP Request' }, step_meta: { h: { type: 'tool.call' } },
    });
    expect(buildRunStory(f, { titleOf: titleOf(f) }).steps[0].hideOutput).toBe(true);
  });
});

describe('runHeadline', () => {
  it('uses the outcome, with the run result underneath', () => {
    expect(runHeadline(run({ outcome: { label: 'Rejected', tone: 'bad' } }))).toEqual({ headline: 'Rejected', sub: 'Run finished in 6 s' });
    expect(runHeadline(run({}))).toEqual({ headline: 'Finished in 6 s', sub: '' });
  });
  it('says how long a stuck run has been stuck', () => {
    const now = Date.parse('2026-10-29T19:16:00Z');
    const r = run({ status: 'Running', stale: true, completed_at: null, modified_at: '2026-10-29T17:15:00Z' });
    expect(runHeadline(r, now).headline).toBe('Stuck for 2 hours');
  });
  it('explains a queued run', () => {
    expect(runHeadline(run({ status: 'Queued', completed_at: null })).headline).toBe('Waiting for a worker');
  });
});

describe('overlayFromRun', () => {
  it('gives each step a status and a short summary, loop bodies included', () => {
    const r = run({
      status: 'Failed', current_node_id: 'f', last_error: 'Fetch page failed: boom',
      context_json: { __node_outputs__: { t: { amount: 5 }, loop: { result: [1, 2] }, body: 'x', f: { error: 'boom', status: 'failed' } } },
      node_labels: { t: 'Webhook', loop: 'Each', body: 'Body', f: 'Fetch page' },
      step_meta: { t: { type: 'trigger.webhook' }, loop: { type: 'foreach', body: ['body'] }, body: { type: 'transform' }, f: { type: 'tool.call' } },
    });
    const o = overlayFromRun(r);
    expect(o.t.status).toBe('done');
    expect(o.t.summary).toContain('5');
    expect(o.loop.summary).toBe('2 rounds');
    expect(o.body.status).toBe('done');
    expect(o.f.status).toBe('failed');
    expect(o.f.summary).toBe('Boom');
    expect(o.missing).toBeUndefined();
  });
});

describe('a loop that stopped part-way', () => {
  const failedLoop = () => run({
    status: 'Failed', current_node_id: 'loop',
    last_error: "The step 'Each order' stopped at item 2: Look up price failed: no price",
    // The step that failed recorded nothing; the one before it worked; the last one never ran this round (its data is from round 1).
    context_json: { __node_outputs__: { t: { n: 1 }, loop: undefined, tidy: { ok: 1 }, price: null, send: { sent: true } } },
    node_labels: { t: 'Webhook', loop: 'Each order', tidy: 'Tidy name', price: 'Look up price', send: 'Send note' },
    step_meta: { t: { type: 'trigger.webhook' }, loop: { type: 'foreach', body: ['tidy', 'price', 'send'] }, tidy: { type: 'transform' }, price: { type: 'tool.call' }, send: { type: 'transform' } },
  });

  it('shows the step that failed as failed and the ones after it as not run, never a green check', () => {
    const story = buildRunStory(failedLoop(), { titleOf: titleOf(failedLoop()) });
    const loop = story.steps.find((s) => s.id === 'loop')!;
    expect(loop.status).toBe('failed');
    expect(loop.children!.map((c) => [c.id, c.status])).toEqual([['tidy', 'done'], ['price', 'failed'], ['send', 'skipped']]);
    expect(loop.reason).toBe('It stopped at item 2 because a step inside it did not work.');
    expect(loop.children![1].reason).toBe('No price');
    expect(loop.children![1].footnote).toBe('Stopped at item 2');
    expect(loop.children![2].footnote).toBe('Not run for item 2');
    expect(loop.children![2].output).toBeUndefined();
  });

  it('gives the canvas the same states', () => {
    const o = overlayFromRun(failedLoop());
    expect(o.price.status).toBe('failed');
    expect(o.send.status).toBe('skipped');
  });
});
