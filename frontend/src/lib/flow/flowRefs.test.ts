import { describe, expect, it } from 'vitest';
import { availableReferences, guaranteedPredecessors, enclosingLoops } from './flowRefs';

const n = (id: string, label: string, nodeType = 'action', y = 0) => ({ id, position: { x: 0, y }, data: { label, nodeType } });
const e = (source: string, target: string, route = 'next') =>
  ({ source, target, sourceHandle: route === 'next' ? null : route, data: { route } });

// trigger -> a -> cond -(true)-> b -> end1 ; cond -(false)-> c -> end2 ; later d after b
const nodes = [n('t', 'Webhook', 'trigger', 0), n('a', 'Fetch', 'action', 1), n('cond', 'Big?', 'action', 2), n('b', 'Big path', 'action', 3), n('c', 'Small path', 'action', 3), n('d', 'After big', 'action', 4)];
const edges = [e('t', 'a'), e('a', 'cond'), e('cond', 'b', 'true'), e('cond', 'c', 'false'), e('b', 'd')];

describe('availableReferences', () => {
  it('lists the trigger and only guaranteed predecessors', () => {
    const refs = availableReferences('d', nodes, edges).map((r) => r.ref);
    expect(refs).toEqual(['input', 'trigger', 'a', 'cond', 'b']);
  });
  it('never lists later steps, the step itself or other branches', () => {
    const refs = availableReferences('b', nodes, edges).map((r) => r.ref);
    expect(refs).not.toContain('d');
    expect(refs).not.toContain('c');
    expect(refs).not.toContain('b');
  });
  it('first step only sees the trigger data', () => {
    expect(availableReferences('a', nodes, edges).map((r) => r.ref)).toEqual(['input', 'trigger']);
  });
  it('a merge point only sees steps on every path', () => {
    const merged = [...edges, e('c', 'd')];
    expect(guaranteedPredecessors('d', nodes, merged)).toEqual(new Set(['t', 'a', 'cond']));
  });
});

describe('loops', () => {
  const ln = [n('t', 'T', 'trigger', 0), n('loop', 'Loop', 'action', 1), n('body', 'Send', 'action', 2), n('done', 'After', 'action', 3)];
  const le = [e('t', 'loop'), e('loop', 'body', 'body'), e('loop', 'done', 'next')];
  it('offers the current item inside a loop body, not the loop itself', () => {
    expect(enclosingLoops('body', ln, le)).toEqual(['loop']);
    const refs = availableReferences('body', ln, le).map((r) => r.ref);
    expect(refs).toContain('foreach.item');
    expect(refs).not.toContain('loop');
  });
  it('collect picker lists the loop body steps', () => {
    expect(availableReferences('loop', ln, le, 'loop-body').map((r) => r.ref)).toEqual(['foreach.item', 'foreach.index', 'body']);
  });
  it('steps after the loop cannot read body steps', () => {
    expect(availableReferences('done', ln, le).map((r) => r.ref)).toEqual(['input', 'trigger', 'loop']);
  });
});
