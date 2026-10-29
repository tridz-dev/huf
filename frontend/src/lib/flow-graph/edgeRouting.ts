/**
 * Orthogonal routing for canvas connections. Pure geometry (no React) so it can be unit-tested.
 *
 * A connection leaves its source straight down, runs along a horizontal "channel" and enters its target from above.
 * When the straight way would cross another step (a branch that skips over a row, a loop that goes back up) the line
 * takes a vertical "gutter" beside the steps instead, so a connection never passes behind a box.
 */

export interface Pt {
  x: number;
  y: number;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Straight distance (px) a line runs out of / into a step before it may turn. */
export const STUB = 32;
/** Clear space kept between a vertical line and the side of a step. */
const SIDE_CLEARANCE = 20;
/** Corner rounding of the drawn line. */
export const CORNER_RADIUS = 12;

export interface RoutedEdge {
  points: Pt[];
  /** SVG path with rounded corners. */
  path: string;
  /** Centre of the branch name pill: just after the line leaves its source. */
  pillAt: Pt;
  /** Pill centre for a connection whose branch name must stay apart from its siblings (several leave one dot): partway along. */
  pillMidAt: Pt;
  /** Centre of the "+" / remove controls: on the last stretch, clear of the arrow head. */
  controlsAt: Pt;
}

const same = (a: number, b: number) => Math.abs(a - b) < 0.5;

/** Whether the axis-aligned segment a-b passes through the rect (touching an edge does not count). */
export function segmentHitsRect(a: Pt, b: Pt, r: Rect, pad = 0): boolean {
  const left = r.x - pad;
  const right = r.x + r.width + pad;
  const top = r.y;
  const bottom = r.y + r.height;
  if (same(a.x, b.x)) {
    const lo = Math.min(a.y, b.y);
    const hi = Math.max(a.y, b.y);
    return a.x > left && a.x < right && hi > top && lo < bottom;
  }
  const lo = Math.min(a.x, b.x);
  const hi = Math.max(a.x, b.x);
  return a.y > top - pad && a.y < bottom + pad && hi > left && lo < right;
}

/** First or last stretch of a route (leaving or entering a step) is exempt: it starts on the step's own border. */
function pathIsClear(points: Pt[], obstacles: Rect[], skipFirst: boolean, skipLast: boolean): boolean {
  for (let i = 0; i < points.length - 1; i++) {
    if ((skipFirst && i === 0) || (skipLast && i === points.length - 2)) continue;
    for (const r of obstacles) if (segmentHitsRect(points[i], points[i + 1], r, 4)) return false;
  }
  return true;
}

function dedupe(points: Pt[]): Pt[] {
  const out: Pt[] = [];
  for (const p of points) {
    const last = out[out.length - 1];
    if (last && same(last.x, p.x) && same(last.y, p.y)) continue;
    // Drop the middle point of three on one line.
    const before = out[out.length - 2];
    if (before && last && ((same(before.x, last.x) && same(last.x, p.x)) || (same(before.y, last.y) && same(last.y, p.y)))) out.pop();
    out.push(p);
  }
  return out;
}

const length = (points: Pt[]) => points.reduce((sum, p, i) => (i === 0 ? 0 : sum + Math.abs(p.x - points[i - 1].x) + Math.abs(p.y - points[i - 1].y)), 0);

/** SVG path through `points` with rounded corners of at most `radius`. */
export function roundedPath(points: Pt[], radius = CORNER_RADIUS): string {
  if (points.length === 0) return '';
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    const next = points[i + 1];
    const inLen = Math.abs(cur.x - prev.x) + Math.abs(cur.y - prev.y);
    const outLen = Math.abs(next.x - cur.x) + Math.abs(next.y - cur.y);
    const r = Math.min(radius, inLen / 2, outLen / 2);
    const start = { x: cur.x - Math.sign(cur.x - prev.x) * r, y: cur.y - Math.sign(cur.y - prev.y) * r };
    const end = { x: cur.x + Math.sign(next.x - cur.x) * r, y: cur.y + Math.sign(next.y - cur.y) * r };
    d += ` L ${start.x} ${start.y} Q ${cur.x} ${cur.y} ${end.x} ${end.y}`;
  }
  const last = points[points.length - 1];
  return `${d} L ${last.x} ${last.y}`;
}

/** Where the branch name pill sits: a little way along the first horizontal run, else on the first stretch. */
function pillPoint(points: Pt[]): Pt {
  const first = points[0];
  const turn = points.find((p, i) => i > 0 && !same(p.x, first.x));
  const channelStart = points[1] ?? first;
  if (turn && Math.abs(turn.x - channelStart.x) >= 80 && points.length > 2) {
    const run = points[2];
    const dir = Math.sign(run.x - channelStart.x) || 1;
    const offset = Math.min(Math.abs(run.x - channelStart.x) / 2, 64);
    return { x: channelStart.x + dir * offset, y: channelStart.y };
  }
  return { x: first.x, y: first.y + STUB / 2 };
}

/** Point `distance` px along the polyline from its start. */
function pointAlong(points: Pt[], distance: number): Pt {
  let left = Math.max(distance, 0);
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const len = Math.abs(b.x - a.x) + Math.abs(b.y - a.y);
    if (left <= len) {
      const t = len === 0 ? 0 : left / len;
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
    }
    left -= len;
  }
  return points[points.length - 1];
}

/** Where the "+" and remove controls sit: on the last stretch, about 30px before the arrow head (or its middle when short). */
function controlsPoint(points: Pt[]): Pt {
  const last = points[points.length - 1];
  const before = points[points.length - 2] ?? last;
  const len = Math.abs(last.x - before.x) + Math.abs(last.y - before.y);
  const back = Math.min(30, len / 2);
  return { x: last.x - Math.sign(last.x - before.x) * back, y: last.y - Math.sign(last.y - before.y) * back };
}

function finish(points: Pt[]): RoutedEdge {
  const clean = dedupe(points);
  return { points: clean, path: roundedPath(clean), pillAt: pillPoint(clean), pillMidAt: pointAlong(clean, length(clean) * 0.4), controlsAt: controlsPoint(clean) };
}

/**
 * Route from the bottom of a source step (`src`) to the top of a target step (`tgt`).
 * `obstacles` are all the steps on the canvas (the two ends included).
 */
export function routeEdge(src: Pt, tgt: Pt, obstacles: Rect[]): RoutedEdge {
  const forward = tgt.y - src.y >= STUB * 2;
  const y1 = forward ? src.y + STUB : src.y + STUB;
  const y2 = forward ? Math.max(y1, tgt.y - STUB) : tgt.y - STUB;

  if (same(src.x, tgt.x) && forward) {
    const straight = [src, tgt];
    if (pathIsClear(straight, obstacles, false, false)) return finish(straight);
  }
  if (forward) {
    const direct = [src, { x: src.x, y: y1 }, { x: tgt.x, y: y1 }, tgt];
    if (pathIsClear(direct, obstacles, true, false)) return finish(direct);
    // Channel just above the target instead (the line then drops straight in).
    const late = [src, { x: src.x, y: y2 }, { x: tgt.x, y: y2 }, tgt];
    if (pathIsClear(late, obstacles, false, true)) return finish(late);
  }

  // Take a gutter beside the steps: down to y1, across to the gutter, along it to y2, across to the target, in.
  const lo = Math.min(y1, y2);
  const hi = Math.max(y1, y2);
  const gutters = new Set<number>([src.x, tgt.x]);
  for (const r of obstacles) {
    if (r.y + r.height < lo - SIDE_CLEARANCE || r.y > hi + SIDE_CLEARANCE) continue;
    gutters.add(r.x - SIDE_CLEARANCE);
    gutters.add(r.x + r.width + SIDE_CLEARANCE);
  }
  let best: Pt[] | null = null;
  for (const gx of gutters) {
    const candidate = [src, { x: src.x, y: y1 }, { x: gx, y: y1 }, { x: gx, y: y2 }, { x: tgt.x, y: y2 }, tgt];
    if (!pathIsClear(candidate, obstacles, true, true)) continue;
    if (!best || length(dedupe(candidate)) < length(dedupe(best))) best = candidate;
  }
  if (best) return finish(best);
  // Nothing is free (very crowded): draw the plain route rather than nothing.
  return finish([src, { x: src.x, y: y1 }, { x: tgt.x, y: y1 }, tgt]);
}

/**
 * Loop-back line: from the bottom of the last step of a loop's body to the right-hand side of the loop step,
 * along a gutter right of everything between them.
 */
export function routeLoopBack(src: Pt, loop: Rect, obstacles: Rect[]): RoutedEdge {
  const entry: Pt = { x: loop.x + loop.width, y: loop.y + loop.height / 2 };
  const y1 = src.y + STUB;
  const lo = Math.min(entry.y, y1);
  const hi = Math.max(entry.y, y1);
  let gx = Math.max(src.x, entry.x) + SIDE_CLEARANCE + 24;
  for (const r of obstacles) {
    if (r.y + r.height < lo - 8 || r.y > hi + 8) continue;
    gx = Math.max(gx, r.x + r.width + SIDE_CLEARANCE);
  }
  return finish([src, { x: src.x, y: y1 }, { x: gx, y: y1 }, { x: gx, y: entry.y }, entry]);
}
