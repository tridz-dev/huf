import { describe, expect, it } from 'vitest';
import { COLUMN_GAP, ROW_GAP, isInView, tidyPositions } from './flowLayout';

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
    const r = panToReveal({ x: 0, y: 1000, width: 100, height: 100 }, { x: 0, y: 0, zoom: 0.5 }, size);
    expect(r?.y).toBe(600 - 24 - 550);
  });
});
