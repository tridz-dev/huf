import { describe, expect, it } from 'vitest';
import { boxAt, overlapArea, pillCandidatesOnLine, pillTouchesLine, placeClear } from './edgePlacement';

const size = { width: 70, height: 20 };

describe('a branch name stays on its own line', () => {
  it('keeps the preferred spot when free', () => {
    const line = [{ x: 100, y: 0 }, { x: 100, y: 200 }];
    const at = placeClear(size, [], { x: 100, y: 40 }, pillCandidatesOnLine(line, { x: 100, y: 40 }, size));
    expect(at).toEqual({ x: 100, y: 40 });
  });

  it('"Approved" slides along its line past a step instead of floating beside it', () => {
    // Vertical line; a step covers its upper part and a wide step sits beside it, leaving free room only far to the side.
    const line = [{ x: 100, y: 0 }, { x: 100, y: 200 }];
    const card = { x: 40, y: 20, width: 236, height: 70 };
    const at = placeClear(size, [card], { x: 100, y: 40 }, pillCandidatesOnLine(line, { x: 100, y: 40 }, size));
    expect(overlapArea(boxAt(at, size), card, 3)).toBe(0);
    expect(pillTouchesLine(line, at, size)).toBe(true);
  });

  it('two names on close lines do not stack and both stay on their lines', () => {
    const left = [{ x: 100, y: 0 }, { x: 100, y: 120 }];
    const right = [{ x: 140, y: 0 }, { x: 140, y: 120 }];
    const first = placeClear(size, [], { x: 100, y: 30 }, pillCandidatesOnLine(left, { x: 100, y: 30 }, size));
    const firstBox = boxAt(first, size);
    const breath = { x: firstBox.x - 8, y: firstBox.y - 5, width: firstBox.width + 16, height: firstBox.height + 10 };
    const second = placeClear(size, [breath], { x: 140, y: 30 }, pillCandidatesOnLine(right, { x: 140, y: 30 }, size));
    expect(overlapArea(boxAt(second, size), firstBox)).toBe(0);
    expect(pillTouchesLine(right, second, size)).toBe(true);
    expect(pillTouchesLine(left, first, size)).toBe(true);
  });

  it('every candidate keeps the line under the pill', () => {
    const line = [{ x: 0, y: 0 }, { x: 0, y: 40 }, { x: 160, y: 40 }, { x: 160, y: 100 }];
    for (const c of pillCandidatesOnLine(line, { x: 160, y: 40 }, size)) expect(pillTouchesLine(line, c, size)).toBe(true);
  });
});
