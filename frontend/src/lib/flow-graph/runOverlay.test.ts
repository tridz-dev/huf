// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { buildRunOverlay } from './runOverlay';

const step = (id: string, extra: Record<string, unknown> = {}, nodeType = 'action') => ({ id, data: { label: id, nodeType, configured: true, ...extra } as never });
const nodes = [step('t', {}, 'trigger'), step('a'), step('b'), step('c'), step('d', { disabled: true })];
const edges = [
  { id: 'e1', source: 't', target: 'a' },
  { id: 'e2', source: 'a', target: 'b' },
  { id: 'e3', source: 'a', target: 'c' },
  { id: 'e4', source: 'b', target: 'd' },
];
const ran = (status: 'done' | 'failed' | 'waiting' | 'stopped', summary = '') => ({ status, summary });

describe('buildRunOverlay', () => {
  it('colours a finished run: ran steps done, the others skipped, taken connections listed', () => {
    const o = buildRunOverlay({ a: ran('done', 'Customer: Ada'), b: ran('done') }, { status: 'Success', currentNodeId: 'b' }, nodes, edges);
    expect(o.nodes.t.status).toBe('done');
    expect(o.nodes.a).toEqual({ status: 'done', summary: 'Customer: Ada' });
    expect(o.nodes.c.status).toBe('skipped');
    expect(o.nodes.d).toEqual({ status: 'skipped', summary: 'Turned off' });
    expect(o.edgesTaken).toEqual(['e1', 'e2']);
  });

  it('keeps the run page\'s reading of a failed step and greys the ones after it', () => {
    const o = buildRunOverlay({ a: ran('done'), b: ran('failed', 'Could not reach the server') }, { status: 'Failed', currentNodeId: 'b' }, nodes, edges);
    expect(o.nodes.b).toEqual({ status: 'failed', summary: 'Could not reach the server' });
    expect(o.nodes.c.status).toBe('skipped');
  });

  it('shows the step a moving run is on as running and leaves steps it has not reached alone', () => {
    const o = buildRunOverlay({ a: ran('done') }, { status: 'Running', currentNodeId: 'b' }, nodes, edges);
    expect(o.nodes.b.status).toBe('running');
    expect(o.nodes.c).toBeUndefined();
    expect(o.edgesTaken).toEqual(['e1', 'e2']);
  });

  it('shows a step waiting for a person and a run stopped by the user', () => {
    expect(buildRunOverlay({ a: ran('done'), b: ran('waiting') }, { status: 'Waiting Approval', currentNodeId: 'b' }, nodes, edges).nodes.b.status).toBe('waiting');
    expect(buildRunOverlay({ a: ran('stopped', 'Stopped by you') }, { status: 'Stopped', currentNodeId: 'a' }, nodes, edges).nodes.a.status).toBe('stopped');
  });

  it('copes with a run that has no recorded step output', () => {
    const o = buildRunOverlay({}, { status: 'Queued', currentNodeId: null }, nodes, edges);
    expect(o.nodes.t.status).toBe('done');
    expect(o.edgesTaken).toEqual([]);
  });
});
