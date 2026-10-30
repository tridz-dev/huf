/**
 * Where the small things drawn over a connection go (its branch name pill, the "+" and remove buttons) so they never sit on
 * each other or on a step. Pure geometry in canvas pixels, so it is unit tested. The pill keeps its preferred spot when it is
 * free and slides along the connection's channel when it is not; the buttons keep their spot on the last stretch when it is
 * free and otherwise move along the line or just beside it, always off the pill.
 */
import type { Pt, Rect } from './edgeRouting';

export interface Size {
  width: number;
  height: number;
}

/** Clear space (canvas px) kept between two things drawn over a connection. */
const MARGIN = 3;
/** Distance (canvas px) between the places tried along a line. */
const STEP = 4;
/** How far (canvas px) a name may slide up or down, and sideways, to get off a step. */
const PILL_REACH_Y = 64;
const PILL_REACH_X = 160;

/**
 * Where every connection's name pill sits right now (by connection id), so the buttons of one connection can keep off the names of
 * the others. Written by the connections as they draw, read when buttons are placed (on hover), so it never causes a redraw.
 */
export const PLACED_PILLS = new Map<string, Rect>();

export const boxAt = (c: Pt, s: Size): Rect => ({ x: c.x - s.width / 2, y: c.y - s.height / 2, width: s.width, height: s.height });

/** Area of the part of `a` that lies on `b` (b grown by `pad` on every side). */
export function overlapArea(a: Rect, b: Rect, pad = 0): number {
  const w = Math.min(a.x + a.width, b.x + b.width + pad) - Math.max(a.x, b.x - pad);
  const h = Math.min(a.y + a.height, b.y + b.height + pad) - Math.max(a.y, b.y - pad);
  return w > 0 && h > 0 ? w * h : 0;
}

/**
 * The first place in `candidates` (best first) where a box of `size` touches nothing in `avoid`; when every place touches
 * something, the one that touches least. `prefer` when there are no candidates.
 */
export function placeClear(size: Size, avoid: Rect[], prefer: Pt, candidates: Iterable<Pt>, pad = MARGIN): Pt {
  let best: Pt | null = null;
  let bestArea = Infinity;
  for (const c of candidates) {
    const box = boxAt(c, size);
    let area = 0;
    for (const r of avoid) {
      area += overlapArea(box, r, pad);
      if (area >= bestArea) break;
    }
    if (area === 0) return c;
    if (area < bestArea) {
      best = c;
      bestArea = area;
    }
  }
  return best ?? prefer;
}

const byDistanceTo = (to: Pt) => (a: { at: Pt; extra: number }, b: { at: Pt; extra: number }) =>
  Math.hypot(a.at.x - to.x, a.at.y - to.y) + a.extra - (Math.hypot(b.at.x - to.x, b.at.y - to.y) + b.extra);

/** Places around the preferred one, nearest first (up or down a lot sooner than sideways): [dx, dy]. */
const PILL_OFFSETS: Array<[number, number]> = (() => {
  const out: Array<[number, number]> = [];
  for (let dy = -PILL_REACH_Y; dy <= PILL_REACH_Y; dy += STEP) for (let dx = -PILL_REACH_X; dx <= PILL_REACH_X; dx += 2 * STEP) out.push([dx, dy]);
  return out.sort((a, b) => Math.abs(a[1]) + 1.5 * Math.abs(a[0]) - (Math.abs(b[1]) + 1.5 * Math.abs(b[0])));
})();

/** The name pill: where it prefers to be, then up or down from there, then (when a card is in the way) beside it. Lazy: usually the first is free. */
export function* pillCandidates(prefer: Pt): Generator<Pt> {
  for (const [dx, dy] of PILL_OFFSETS) yield { x: prefer.x + dx, y: prefer.y + dy };
}

/** Point `distance` px along a polyline and the way the line runs there (true = across, false = up or down). */
function along(points: Pt[], distance: number): { at: Pt; horizontal: boolean } {
  let left = Math.max(distance, 0);
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const len = Math.abs(b.x - a.x) + Math.abs(b.y - a.y);
    if (left <= len) {
      const t = len === 0 ? 0 : left / len;
      return { at: { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }, horizontal: Math.abs(b.y - a.y) < 0.5 };
    }
    left -= len;
  }
  const last = points[points.length - 1];
  return { at: last, horizontal: false };
}

/**
 * Places for the "+" / remove buttons, best first: where they prefer to be, then further along the line, then just beside it
 * (a little less good than on it, so they only move off the line when it has no free stretch).
 */
export function controlCandidates(points: Pt[], length: number, size: Size, prefer: Pt): Pt[] {
  const scored: Array<{ at: Pt; extra: number }> = [{ at: prefer, extra: 0 }];
  for (let d = 0; d <= length; d += STEP) {
    const { at, horizontal } = along(points, d);
    scored.push({ at, extra: 0 });
    const side = (horizontal ? size.height : size.width) / 2 + MARGIN + 6;
    // Further out (up to six more tries) when a name sits where the first try would land.
    for (let k = 0; k < 7; k++) {
      for (const sign of [1, -1]) {
        const s = sign * (side + 24 * k);
        scored.push({ at: horizontal ? { x: at.x, y: at.y + s } : { x: at.x + s, y: at.y }, extra: 40 + 12 * k });
      }
    }
  }
  return scored.sort(byDistanceTo(prefer)).map((s) => s.at);
}
