import { describe, expect, it } from 'vitest';
import { routeEdge, routeLoopBack, segmentHitsRect, type Pt, type Rect } from './edgeRouting';

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
