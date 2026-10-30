import { describe, expect, it } from 'vitest';
import { boxAt, controlCandidates, overlapArea, pillCandidates, placeClear } from './edgePlacement';

const card = { x: 0, y: 0, width: 236, height: 70 };

describe('placing things over a connection', () => {
  it('keeps the preferred place when it is free', () => {
    const at = placeClear({ width: 40, height: 20 }, [card], { x: 118, y: 100 }, pillCandidates({ x: 118, y: 100 }));
    expect(at).toEqual({ x: 118, y: 100 });
  });

  it('slides a name that would cover a step into the free space beside it', () => {
    // A tall name (a 12px label seen at 25% zoom) centred just under the card would cut into it.
    const size = { width: 120, height: 60 };
    const at = placeClear(size, [card], { x: 118, y: 90 }, pillCandidates({ x: 118, y: 90 }));
    expect(overlapArea(boxAt(at, size), card)).toBe(0);
    expect(at.y).toBeGreaterThan(90);
  });

  it('moves a name that cannot fit between two steps to the side of them', () => {
    // Two icon tiles 50px apart and a name 70px tall: it cannot fit between them.
    const upper = { x: 58, y: 0, width: 120, height: 70 };
    const lower = { x: 58, y: 120, width: 120, height: 70 };
    const size = { width: 100, height: 70 };
    const at = placeClear(size, [upper, lower], { x: 118, y: 95 }, pillCandidates({ x: 118, y: 95 }));
    expect(overlapArea(boxAt(at, size), upper)).toBe(0);
    expect(overlapArea(boxAt(at, size), lower)).toBe(0);
  });

  it('puts the buttons beside the line when the line has no free stretch, never on the name', () => {
    const points = [{ x: 118, y: 70 }, { x: 118, y: 120 }];
    const pill = boxAt({ x: 118, y: 95 }, { width: 40, height: 20 });
    const size = { width: 62, height: 28 };
    const prefer = { x: 118, y: 100 };
    const at = placeClear(size, [card, pill], prefer, controlCandidates(points, 50, size, prefer));
    expect(overlapArea(boxAt(at, size), pill)).toBe(0);
    expect(overlapArea(boxAt(at, size), card)).toBe(0);
  });

  it('keeps the buttons on the line when the name is elsewhere', () => {
    const points = [{ x: 118, y: 70 }, { x: 118, y: 200 }];
    const pill = boxAt({ x: 118, y: 90 }, { width: 40, height: 20 });
    const size = { width: 28, height: 28 };
    const prefer = { x: 118, y: 170 };
    const at = placeClear(size, [card, pill], prefer, controlCandidates(points, 130, size, prefer));
    expect(at).toEqual(prefer);
  });

  it('moves the "+" off the name when the steps are only a few px apart', () => {
    const above = { x: 0, y: 0, width: 236, height: 70 };
    const below = { x: 0, y: 74, width: 236, height: 70 };
    const points = [{ x: 118, y: 70 }, { x: 118, y: 74 }];
    const pill = boxAt({ x: 118, y: 72 }, { width: 40, height: 20 });
    const size = { width: 28, height: 28 };
    const prefer = { x: 118, y: 72 };
    const at = placeClear(size, [above, below, pill], prefer, controlCandidates(points, 4, size, prefer));
    expect(overlapArea(boxAt(at, size), pill, 3)).toBe(0);
  });
});
