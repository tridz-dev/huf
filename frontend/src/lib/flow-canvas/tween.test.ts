import { describe, expect, it } from 'vitest';
import { blendPositions } from './tween';

describe('blendPositions', () => {
  const from = { a: { x: 0, y: 0 }, b: { x: 100, y: 100 } };
  const to = { a: { x: 100, y: 200 }, b: { x: 100, y: 100 }, c: { x: 5, y: 5 } };
  it('starts at the old layout and ends exactly on the new one', () => {
    expect(blendPositions(from, to, 0).a).toEqual({ x: 0, y: 0 });
    expect(blendPositions(from, to, 1)).toEqual(to);
  });
  it('is halfway at the middle of the time and puts new steps straight in place', () => {
    const mid = blendPositions(from, to, 0.5);
    expect(mid.a).toEqual({ x: 50, y: 100 });
    expect(mid.c).toEqual({ x: 5, y: 5 });
  });
});
