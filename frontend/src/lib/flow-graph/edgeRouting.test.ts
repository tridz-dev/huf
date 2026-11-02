import { describe, expect, it } from 'vitest';
import { roundedPath, routeEdge, routeLoopBack, segmentHitsRect, shortLinePill, type Pt, type Rect } from './edgeRouting';

const box = (x: number, y: number, width = 236, height = 70): Rect => ({ x, y, width, height });
const hitsAny = (points: Pt[], rects: Rect[], skip: Rect[] = []) =>
  points.slice(0, -1).some((p, i) => rects.some((r) => !skip.includes(r) && segmentHitsRect(p, points[i + 1], r)));

describe('routeEdge', () => {
  it('draws a straight line between steps in one column', () => {
    const routed = routeEdge({ x: 118, y: 70 }, { x: 118, y: 220 }, []);
    expect(routed.points).toEqual([{ x: 118, y: 70 }, { x: 118, y: 220 }]);
  });

  it('turns in the channel under the source for a side branch', () => {
    const routed = routeEdge({ x: 118, y: 70 }, { x: 408, y: 220 }, []);
    expect(routed.points.map((p) => p.y)).toEqual([70, 102, 102, 220]);
    expect(routed.pillAt.y).toBe(102);
  });

  it('goes around a step that sits in the way (router edge skipping a row)', () => {
    // Source at the top, target two rows down in the same column, another step between them.
    const middle = box(0, 150);
    const src = { x: 118, y: 70 };
    const tgt = { x: 118, y: 300 };
    const routed = routeEdge(src, tgt, [box(0, 0), middle, box(0, 300)]);
    expect(hitsAny(routed.points, [middle])).toBe(false);
    expect(routed.points.length).toBeGreaterThan(2);
  });

  it('never crosses any step on a crowded canvas', () => {
    const rects = [box(0, 0), box(-290, 150), box(0, 150), box(290, 150), box(0, 300), box(290, 300)];
    const routed = routeEdge({ x: 118, y: 70 }, { x: 408, y: 300 }, rects);
    expect(hitsAny(routed.points, rects, [rects[0], rects[5]])).toBe(false);
  });

  it('routes a target above the source around the steps', () => {
    const rects = [box(0, 0), box(0, 150)];
    const routed = routeEdge({ x: 118, y: 220 }, { x: 118, y: 0 }, rects);
    expect(hitsAny(routed.points.slice(1, -1), rects)).toBe(false);
  });
});

describe('routeLoopBack', () => {
  it('returns to the right-hand side of the loop along a gutter clear of the steps', () => {
    const loop = box(0, 0);
    const body = box(0, 150);
    const routed = routeLoopBack({ x: 118, y: 220 }, loop, [loop, body]);
    const last = routed.points[routed.points.length - 1];
    expect(last).toEqual({ x: 236, y: 35 });
    expect(routed.points.some((p) => p.x > 236)).toBe(true);
    expect(hitsAny(routed.points.slice(1), [body])).toBe(false);
  });
});

describe('w1cap-05: a sideways run keeps off the arrow of a sibling that goes straight down', () => {
  const triage: Pt = { x: 118, y: 100 };
  const below: Rect = { x: 0, y: 150, width: 236, height: 100 };
  it('turns sooner when a step sits 50px under the source', () => {
    const routed = routeEdge(triage, { x: 420, y: 330 }, [below, { x: 302, y: 330, width: 236, height: 100 }]);
    expect(routed.points[1].y).toBeLessThanOrEqual(triage.y + 16);
    expect(routed.points[1].y).toBeLessThan(below.y - 30);
  });
  it('keeps the usual distance when there is room', () => {
    const routed = routeEdge(triage, { x: 420, y: 330 }, [{ x: 302, y: 330, width: 236, height: 100 }]);
    expect(routed.points[1].y).toBe(triage.y + 32);
  });
});

describe('final2-02: a short straight line names itself under the sibling that turns sideways', () => {
  it('the name of a 50px line sits below the sibling run, above the arrow head', () => {
    const triage: Pt = { x: 118, y: 100 };
    const below: Rect = { x: 0, y: 150, width: 236, height: 100 };
    const straight = routeEdge(triage, { x: 118, y: 150 }, [below]);
    const sideways = routeEdge(triage, { x: 420, y: 330 }, [below, { x: 302, y: 330, width: 236, height: 100 }]);
    const run = sideways.points[1].y;
    expect(straight.pillAt.y - 10).toBeGreaterThan(run + 4); // name's top clears the sibling's level run
    expect(straight.pillAt.y + 10).toBeLessThanOrEqual(150 - 8); // and its bottom the arrow head
  });
  it('a long straight line keeps its name 16px under the step', () => {
    expect(routeEdge({ x: 118, y: 70 }, { x: 118, y: 220 }, []).pillAt.y).toBe(86);
  });
});

describe('ux41: one rule for a name on a short straight line', () => {
  it('shortLinePill is the pillAt of a short line, 21px above the arrow head, and null for a long or bent line', () => {
    const short = routeEdge({ x: 118, y: 100 }, { x: 118, y: 150 }, []);
    expect(shortLinePill(short.points)).toEqual(short.pillAt);
    expect(short.pillAt.y).toBe(100 + 50 - 21);
    expect(shortLinePill(routeEdge({ x: 118, y: 70 }, { x: 118, y: 220 }, []).points)).toBeNull();
    expect(shortLinePill(routeEdge({ x: 118, y: 100 }, { x: 420, y: 330 }, []).points)).toBeNull();
  });
  it('the cut-off is the same for the plain name and the option name (62px: short, 64px: not)', () => {
    expect(shortLinePill(routeEdge({ x: 0, y: 0 }, { x: 0, y: 63 }, []).points)).not.toBeNull();
    expect(shortLinePill(routeEdge({ x: 0, y: 0 }, { x: 0, y: 64 }, []).points)).toBeNull();
  });
});

describe('roundedPath', () => {
  it('stays square when the coordinates carry float noise (final2 diagonal lines on the demo flows)', () => {
    const d = roundedPath([{ x: 353.65628, y: 364 }, { x: 353.65628, y: 384 }, { x: 248, y: 384.0000228 }, { x: 248, y: 416.0000228 }]);
    const nums = d.match(/-?\d+(\.\d+)?/g)!.map(Number);
    // Q control then end: each move from the control point to the end must be along one axis only.
    const q = [...d.matchAll(/Q ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)/g)];
    expect(q.length).toBe(2);
    for (const m of q) {
      const [cx, cy, ex, ey] = m.slice(1).map(Number);
      expect(Math.abs(cx - ex) < 0.5 || Math.abs(cy - ey) < 0.5).toBe(true);
    }
    expect(nums.length).toBeGreaterThan(8);
  });
});
