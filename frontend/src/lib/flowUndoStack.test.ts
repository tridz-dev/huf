import { describe, it, expect } from 'vitest';
import { pushSnapshot, popSnapshot } from './flowUndoStack';

type Snap = { nodes: string[]; edges: string[] };
const snap = (n: string): Snap => ({ nodes: [n], edges: [] });

describe('flowUndoStack', () => {
  it('pushes snapshots in order and pops the most recent first', () => {
    let stack = pushSnapshot<string, string>([], snap('a'), 20);
    stack = pushSnapshot(stack, snap('b'), 20);

    const first = popSnapshot(stack);
    expect(first.snapshot).toEqual(snap('b'));
    const second = popSnapshot(first.rest);
    expect(second.snapshot).toEqual(snap('a'));
    expect(second.rest).toEqual([]);
  });

  it('caps history at the limit, dropping the oldest entries', () => {
    let stack: Snap[] = [];
    for (const id of ['a', 'b', 'c', 'd']) {
      stack = pushSnapshot(stack, snap(id), 3);
    }
    expect(stack.map(s => s.nodes[0])).toEqual(['b', 'c', 'd']);
  });

  it('returns no snapshot when empty', () => {
    const result = popSnapshot<string, string>([]);
    expect(result.snapshot).toBeUndefined();
    expect(result.rest).toEqual([]);
  });

  it('does not mutate the input stack', () => {
    const stack = [snap('a')];
    pushSnapshot(stack, snap('b'), 20);
    popSnapshot(stack);
    expect(stack).toEqual([snap('a')]);
  });
});
