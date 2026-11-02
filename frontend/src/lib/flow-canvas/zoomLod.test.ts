import { describe, expect, it } from 'vitest';
import { compactGrowth, counterScale, hoverTitlePx, lodForKey, lodForZoom, tileIconSize, zoomKey, zoomOfKey } from './zoomLod';

describe('lodForZoom', () => {
  it('shows the full card from 80% up', () => {
    expect(lodForZoom(1.5)).toBe('full');
    expect(lodForZoom(1)).toBe('full');
    expect(lodForZoom(0.8)).toBe('full');
  });
  it('shows icon, title and status dot from 50% to just under 80%', () => {
    expect(lodForZoom(0.79)).toBe('compact');
    expect(lodForZoom(0.6)).toBe('compact');
    expect(lodForZoom(0.5)).toBe('compact');
  });
  it('shows the icon tile under 50%', () => {
    expect(lodForZoom(0.49)).toBe('icon');
    expect(lodForZoom(0.25)).toBe('icon');
  });
});

describe('zoomKey', () => {
  it('is one value for the whole full range so zooming in does not re-render cards', () => {
    expect(new Set([0.8, 0.9, 1, 1.25, 1.5].map(zoomKey))).toEqual(new Set([20]));
  });
  it('agrees with lodForZoom at every 1% step', () => {
    for (let z = 0.25; z <= 1.5; z += 0.01) {
      const zoom = Math.round(z * 100) / 100;
      expect(lodForKey(zoomKey(zoom))).toBe(lodForZoom(zoom));
    }
  });
  it('never gives a zoom outside the canvas range', () => {
    expect(zoomOfKey(zoomKey(0.25))).toBeCloseTo(0.25);
    expect(zoomOfKey(zoomKey(0.1))).toBeGreaterThanOrEqual(0.25);
  });
});

describe('counterScale', () => {
  it('keeps a label at 12px on screen at every zoom of the canvas', () => {
    for (const zoom of [0.25, 0.4, 0.5, 0.75, 1, 1.25, 1.5]) {
      expect(12 * zoom * counterScale(zoom)).toBeCloseTo(12, 5);
    }
  });
  it('is capped and survives a zero zoom', () => {
    expect(counterScale(0.01)).toBe(4);
    expect(counterScale(0)).toBe(1);
  });
});

describe('compact content', () => {
  it('grows as the canvas shrinks but stays inside the card', () => {
    expect(compactGrowth(0.8)).toBeCloseTo(1.1875, 3);
    expect(compactGrowth(0.5)).toBeCloseTo(1.7, 5);
    expect(compactGrowth(1)).toBe(1);
  });
  it('keeps a 14px title at 11.8px or more on screen at 50%', () => {
    expect(14 * compactGrowth(0.5) * 0.5).toBeGreaterThanOrEqual(11.8);
  });
});

describe('icon tile', () => {
  it('keeps the icon about 26px on screen from 49% down to 41%, then lets it shrink', () => {
    expect(tileIconSize(0.49) * 0.49).toBeGreaterThan(24);
    expect(tileIconSize(0.25) * 0.25).toBeLessThan(26);
    expect(tileIconSize(0.25)).toBe(64);
  });
  it('draws the hover title at 12px on screen', () => {
    expect(hoverTitlePx(0.25) * 0.25).toBeCloseTo(12, 1);
    expect(hoverTitlePx(0.4) * 0.4).toBeCloseTo(12, 1);
  });
});
