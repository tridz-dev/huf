import { describe, expect, it } from 'vitest';
import { PLACED_PILLS, boxAt, forgetPill, getPlacedVersion, controlCandidates, overlapArea, levelRuns, recordRuns, forgetRuns, runsOfOthers, pillCandidates, pillsBefore, placeClear, recordPill } from './edgePlacement';

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

describe('names that meet (w1cap-05)', () => {
  it('a name keeps off the names of the connections before it, never the ones after', () => {
    PLACED_PILLS.clear();
    recordPill('a-approved', { x: 100, y: 200, width: 70, height: 20 });
    recordPill('b-rejected', { x: 130, y: 200, width: 70, height: 20 });
    expect(pillsBefore('b-rejected')).toEqual([{ x: 100, y: 200, width: 70, height: 20 }]);
    expect(pillsBefore('a-approved')).toEqual([]);
    const size = { width: 70, height: 20 };
    const prefer = { x: 165, y: 210 };
    const spot = placeClear(size, pillsBefore('b-rejected'), prefer, pillCandidates(prefer));
    const box = boxAt(spot, size);
    expect(overlapArea(box, { x: 100, y: 200, width: 70, height: 20 })).toBe(0);
    PLACED_PILLS.clear();
  });

  it('recording a name that did not move does not wake the others (no endless re-placing)', () => {
    PLACED_PILLS.clear();
    recordPill('a', { x: 10, y: 10, width: 50, height: 20 });
    const v = getPlacedVersion();
    recordPill('a', { x: 10.2, y: 10, width: 50, height: 20 });
    expect(getPlacedVersion()).toBe(v);
    recordPill('a', { x: 40, y: 10, width: 50, height: 20 });
    expect(getPlacedVersion()).toBe(v + 1);
    forgetPill('a');
    expect(getPlacedVersion()).toBe(v + 2);
    PLACED_PILLS.clear();
  });
});

describe('final2-02: a name keeps off the level runs of other connections', () => {
  it('levelRuns lists only the level stretches (corners do not count)', () => {
    const runs = levelRuns([{ x: 100, y: 0 }, { x: 100, y: 14 }, { x: 300, y: 14 }, { x: 300, y: 80 }]);
    expect(runs).toEqual([{ x: 100, y: 12.5, width: 200, height: 3 }]);
  });
  it('a name is placed off another connection\'s run, and ignores its own', () => {
    recordRuns('a', levelRuns([{ x: 100, y: 0 }, { x: 100, y: 14 }, { x: 300, y: 14 }]));
    expect(runsOfOthers('a')).toEqual([]);
    const others = runsOfOthers('b');
    expect(others.length).toBe(1);
    const size = { width: 50, height: 20 };
    const spot = placeClear(size, others, { x: 150, y: 14 }, pillCandidates({ x: 150, y: 14 }));
    expect(overlapArea(boxAt(spot, size), others[0], 3)).toBe(0);
    forgetRuns('a');
    expect(runsOfOthers('b')).toEqual([]);
  });
});
