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
});
