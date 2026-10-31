import { describe, expect, it } from 'vitest';
import { clearOfSteps } from './cloneSteps';

describe('clearOfSteps', () => {
  const at = (id: string, x: number, y: number) => ({ id, position: { x, y }, width: 236, height: 100, data: {} }) as never;
  it('moves copies down until they sit on no other step', () => {
    const out = clearOfSteps([at('c', 48, 72)], [at('a', 0, 0)]);
    expect(out[0].position).toEqual({ x: 48, y: 72 + 48 });
    // Below is taken by another step: one column over instead.
    const side = clearOfSteps([at('c', 48, 72)], [at('a', 0, 0), at('b', 0, 160)]);
    expect(side[0].position).toEqual({ x: 48 + 284, y: 72 });
  });
  it('leaves copies that already have room, and keeps a group together', () => {
    expect(clearOfSteps([at('c', 400, 0)], [at('a', 0, 0)])[0].position).toEqual({ x: 400, y: 0 });
    const out = clearOfSteps([at('c1', 48, 72), at('c2', 48, 200)], [at('a', 0, 0)]);
    expect(out[1].position.y - out[0].position.y).toBe(128);
  });
  it('tries a short nudge down, then a column right, then further down, then gives up', () => {
    // Below is taken for the 3 nudges and the column is free: the column wins over a long drop.
    const col = clearOfSteps([at('c', 0, 0)], [at('a', 0, 0), at('b', 0, 130)]);
    expect(col[0].position.x).toBe(284);
    // Both columns blocked within 3 nudges: further down, up to 288px.
    const blockers = [at('a', 0, 0), at('b', 0, 130), at('d', 284, 0), at('e', 284, 130), at('f', 568, 0), at('g', 568, 130)];
    const far = clearOfSteps([at('c', 0, 0)], blockers);
    expect(far[0].position.x).toBe(0);
    expect(far[0].position.y).toBeGreaterThan(72);
    // Nothing clears: the copies stay as placed.
    const wall = [at('w', -100, -100)];
    (wall[0] as { width: number; height: number }).width = 5000;
    (wall[0] as { width: number; height: number }).height = 5000;
    expect(clearOfSteps([at('c', 0, 0)], wall)[0].position).toEqual({ x: 0, y: 0 });
  });
});
