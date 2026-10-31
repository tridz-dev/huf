import { describe, expect, it } from 'vitest';
import { COLUMN_GAP, ROW_GAP, hasCrowdedSteps, isInView, layoutWhenUnplaced, tidyPositions } from './flowLayout';

const n = (id: string, x = 0, y = 0) => ({ id, position: { x, y } });

describe('tidyPositions', () => {
  it('lines a straight run up vertically', () => {
    const p = tidyPositions([n('a', 5, 900), n('b', 400, 10), n('c', -50, 300)], [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'c' },
    ]);
    expect(p.a).toEqual({ x: 250, y: 100 });
    expect(p.b).toEqual({ x: 250, y: 100 + ROW_GAP });
    expect(p.c).toEqual({ x: 250, y: 100 + 2 * ROW_GAP });
  });

  it('fans a branch out under its router and joins below both paths', () => {
    const p = tidyPositions([n('t'), n('r'), n('x'), n('y'), n('end')], [
      { source: 't', target: 'r' },
      { source: 'r', target: 'x' },
      { source: 'r', target: 'y' },
      { source: 'x', target: 'end' },
      { source: 'y', target: 'end' },
    ]);
    expect(p.x.y).toBe(p.y.y);
    expect(p.y.x - p.x.x).toBe(COLUMN_GAP);
    expect(p.r.x).toBe(250);
    expect(p.end.y).toBe(100 + 3 * ROW_GAP);
    expect(p.end.x).toBe((p.x.x + p.y.x) / 2);
  });

  it('survives a loop and a disconnected step', () => {
    const p = tidyPositions([n('a'), n('b'), n('lone')], [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'a' },
    ]);
    expect(Object.keys(p).sort()).toEqual(['a', 'b', 'lone']);
    for (const v of Object.values(p)) expect(Number.isFinite(v.x) && Number.isFinite(v.y)).toBe(true);
  });
});

describe('isInView', () => {
  const size = { width: 840, height: 850 };
  it('is true for content well inside the canvas', () => {
    expect(isInView({ x: 100, y: 100, width: 200, height: 300 }, { x: 0, y: 0, zoom: 1 }, size)).toBe(true);
  });
  it('is false when a step hangs below, beside or under the toolbar', () => {
    expect(isInView({ x: 100, y: 100, width: 200, height: 900 }, { x: 0, y: 0, zoom: 1 }, size)).toBe(false);
    expect(isInView({ x: 700, y: 100, width: 200, height: 100 }, { x: 0, y: 0, zoom: 1 }, size)).toBe(false);
    expect(isInView({ x: 100, y: -20, width: 200, height: 100 }, { x: 0, y: 0, zoom: 1 }, size)).toBe(false);
  });
  it('accounts for zoom and pan', () => {
    expect(isInView({ x: 100, y: 100, width: 400, height: 1400 }, { x: 0, y: 0, zoom: 0.5 }, size)).toBe(true);
    expect(isInView({ x: 100, y: 100, width: 200, height: 100 }, { x: -200, y: 0, zoom: 1 }, size)).toBe(false);
  });
});

import { panToReveal } from './flowLayout';
describe('panToReveal', () => {
  const size = { width: 800, height: 600 };
  it('does nothing when the box is fully visible', () => {
    expect(panToReveal({ x: 10, y: 10, width: 100, height: 50 }, { x: 0, y: 0, zoom: 1 }, size)).toBeNull();
  });
  it('pans up just enough for a box below the canvas, keeping x', () => {
    const r = panToReveal({ x: 100, y: 700, width: 200, height: 60 }, { x: 0, y: 0, zoom: 1 }, size);
    expect(r).toEqual({ x: 0, y: -(760 - (600 - 24)) });
  });
  it('accounts for zoom', () => {
    const r = panToReveal({ x: 0, y: 2000, width: 100, height: 100 }, { x: 0, y: 0, zoom: 0.5 }, size);
    expect(r?.y).toBe(600 - 24 - 1050);
  });
  it('lifts a box that would sit under the bottom-left overlays', () => {
    const covered = { x: 0, y: 450, width: 270, height: 150 };
    // Fully inside the canvas but under the overview: moved up so its bottom clears the overlay by the padding.
    const r = panToReveal({ x: 100, y: 500, width: 200, height: 60 }, { x: 0, y: 0, zoom: 1 }, size, 24, covered);
    expect(r).toEqual({ x: 0, y: -(560 - (450 - 24)) });
  });
  it('final2-03: brings a box that sits under the floating toolbar down below it', () => {
    const r = panToReveal({ x: 100, y: 10, width: 200, height: 60 }, { x: 0, y: 0, zoom: 1 }, size, 24, undefined, 56);
    expect(r).toEqual({ x: 0, y: 56 + 24 - 10 });
    expect(panToReveal({ x: 100, y: 100, width: 200, height: 60 }, { x: 0, y: 0, zoom: 1 }, size, 24, undefined, 56)).toBeNull();
  });
  it('leaves a box that is clear of the overlays alone', () => {
    const covered = { x: 0, y: 450, width: 270, height: 150 };
    expect(panToReveal({ x: 400, y: 500, width: 200, height: 60 }, { x: 0, y: 0, zoom: 1 }, size, 24, covered)).toBeNull();
  });
});

describe('w1cap-05: steps squeezed side by side', () => {
  it('spots two cards 4px apart (the Loop demo) and not a normal branch pair', () => {
    expect(hasCrowdedSteps([n('a', 130, 400), n('b', 370, 400)])).toBe(true);
    expect(hasCrowdedSteps([n('a', 130, 400), n('b', 130 + COLUMN_GAP, 400)])).toBe(false);
    expect(hasCrowdedSteps([n('a', 250, 250), n('b', 250, 250 + ROW_GAP)])).toBe(false);
  });

  it('needs a real overlap on both axes, not just two top-left corners that are close', () => {
    // Same column, 130px apart: the corners are near but the boxes (100px tall) do not touch.
    expect(hasCrowdedSteps([n('a', 250, 250), n('b', 250, 380)])).toBe(false);
    // 100px apart horizontally is far less than a card width, yet a whole row above is clear.
    expect(hasCrowdedSteps([n('a', 250, 250), n('b', 350, 250 + 200)])).toBe(false);
    // Boxes really overlapping on both axes.
    expect(hasCrowdedSteps([n('a', 250, 250), n('b', 350, 300)])).toBe(true);
    // Side by side with the old 24px gap but not touching: left alone.
    expect(hasCrowdedSteps([n('a', 130, 400), n('b', 130 + 236 + 20, 400)])).toBe(false);
  });

  it('re-tidies only the group that holds the crowded cards; other groups keep their saved spots', () => {
    const edges = [
      { source: 't', target: 'a' }, { source: 't', target: 'b' },
      { source: 'x', target: 'y' },
    ];
    const nodes = [n('t', 250, 250), n('a', 130, 400), n('b', 370, 400), n('x', 1200, 250), n('y', 1213, 411)];
    const out = layoutWhenUnplaced(nodes, edges, false);
    expect(out[3].position).toEqual({ x: 1200, y: 250 });
    expect(out[4].position).toEqual({ x: 1213, y: 411 });
    expect(Math.abs(out[2].position.x - out[1].position.x)).toBeGreaterThanOrEqual(COLUMN_GAP);
    expect(Math.min(...out.slice(0, 3).map((o) => o.position.x))).toBe(130); // same top-left corner as before
  });

  it('lays a squeezed flow out again on load, and leaves a roomy one alone', () => {
    const edges = [{ source: 't', target: 'a' }, { source: 't', target: 'b' }];
    const squeezed = [n('t', 250, 250), n('a', 130, 400), n('b', 370, 400)];
    const out = layoutWhenUnplaced(squeezed, edges, false);
    expect(Math.abs(out[2].position.x - out[1].position.x)).toBeGreaterThanOrEqual(COLUMN_GAP);
    const roomy = [n('t', 250, 250), n('a', 100, 400), n('b', 100 + COLUMN_GAP, 400)];
    expect(layoutWhenUnplaced(roomy, edges, false)).toBe(roomy);
  });
});
