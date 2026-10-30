// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { buildRunOverlay, stepSummary } from './runOverlay';

const step = (id: string, extra: Record<string, unknown> = {}, nodeType = 'action') => ({ id, data: { label: id, nodeType, configured: true, ...extra } as never });
const nodes = [step('t', {}, 'trigger'), step('a'), step('b'), step('c'), step('d', { disabled: true })];
const edges = [
  { id: 'e1', source: 't', target: 'a' },
  { id: 'e2', source: 'a', target: 'b' },
  { id: 'e3', source: 'a', target: 'c' },
  { id: 'e4', source: 'b', target: 'd' },
];

describe('buildRunOverlay', () => {
  it('colours a finished run: ran steps done, the others skipped, taken connections listed', () => {
    const o = buildRunOverlay(
      { status: 'Success', current_node_id: 'b', last_error: null, context_json: { __node_outputs__: { a: { total: 450, customer: 'Ada' }, b: { ok: true } } } },
      nodes,
      edges,
    );
    expect(o.nodes.t.status).toBe('done');
    expect(o.nodes.a.status).toBe('done');
    expect(o.nodes.b.status).toBe('done');
    expect(o.nodes.c.status).toBe('skipped');
    expect(o.nodes.d.status).toBe('skipped');
    expect(o.edgesTaken).toEqual(['e1', 'e2']);
    expect(o.nodes.a.summary).toContain('Ada');
  });

  it('marks the step a failed run stopped at, with its reason', () => {
    const o = buildRunOverlay(
      { status: 'Failed', current_node_id: 'b', last_error: 'Could not reach the server', context_json: { __node_outputs__: { a: { ok: true } } } },
      nodes,
      edges,
    );
    expect(o.nodes.b).toEqual({ status: 'failed', summary: 'Could not reach the server' });
    expect(o.nodes.c.status).toBe('skipped');
  });

  it('treats a step whose own result says it failed as failed', () => {
    const o = buildRunOverlay({ status: 'Success', current_node_id: '', last_error: null, context_json: { __node_outputs__: { a: { success: false, error: 'No such sheet' } } } }, nodes, edges);
    expect(o.nodes.a).toEqual({ status: 'failed', summary: 'No such sheet' });
  });

  it('shows running and waiting steps and leaves not-yet-reached steps alone', () => {
    const running = buildRunOverlay({ status: 'Running', current_node_id: 'b', last_error: null, context_json: { __node_outputs__: { a: { ok: 1 } } } }, nodes, edges);
    expect(running.nodes.b.status).toBe('running');
    expect(running.nodes.c).toBeUndefined();
    const waiting = buildRunOverlay({ status: 'Waiting Approval', current_node_id: 'b', last_error: null, context_json: { __node_outputs__: { a: { ok: 1 } } } }, nodes, edges);
    expect(waiting.nodes.b.status).toBe('waiting');
    expect(waiting.edgesTaken).toContain('e2');
  });

  it('copes with a run that has no recorded output', () => {
    const o = buildRunOverlay({ status: 'Queued', current_node_id: '', last_error: null, context_json: {} }, nodes, edges);
    expect(o.nodes.t.status).toBe('done');
    expect(o.edgesTaken).toEqual([]);
  });
});

describe('stepSummary', () => {
  it('is one short line, empty for no output, and never shows secrets', () => {
    expect(stepSummary(step('a'), undefined)).toBe('');
    expect(stepSummary(step('a'), { token: 'sk-live-abcdefghijklmnop1234', name: 'Ada' })).not.toContain('sk-live');
    expect(stepSummary(step('a'), { text: 'x'.repeat(400) }).length).toBeLessThanOrEqual(110);
    expect(stepSummary(step('a'), { decision: 'approved' })).not.toBe('');
  });
});
