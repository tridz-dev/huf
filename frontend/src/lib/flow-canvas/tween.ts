/** Small animation helpers for the canvas. Nothing here moves when the person asked their system for reduced motion. */

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Length (ms) of a view or layout animation: 0 when motion is reduced. */
export function motionMs(ms: number): number {
  return prefersReducedMotion() ? 0 : ms;
}

type Point = { x: number; y: number };
const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

/** Positions between two layouts at progress `t` (0..1, eased). Steps missing from `from` jump straight to `to`. */
export function blendPositions(from: Record<string, Point>, to: Record<string, Point>, t: number): Record<string, Point> {
  const k = easeInOut(Math.min(Math.max(t, 0), 1));
  const out: Record<string, Point> = {};
  for (const [id, end] of Object.entries(to)) {
    const start = from[id];
    out[id] = start ? { x: start.x + (end.x - start.x) * k, y: start.y + (end.y - start.y) * k } : end;
  }
  return out;
}

/** Runs `frame(t)` on every animation frame for `ms`, ending exactly on t = 1. Returns a function that stops it. */
export function runFrames(ms: number, frame: (t: number) => void, done?: () => void): () => void {
  if (ms <= 0 || typeof requestAnimationFrame !== 'function') {
    frame(1);
    done?.();
    return () => undefined;
  }
  let raf = 0;
  let start = 0;
  const step = (now: number) => {
    if (!start) start = now;
    const t = Math.min((now - start) / ms, 1);
    frame(t);
    if (t < 1) raf = requestAnimationFrame(step);
    else done?.();
  };
  raf = requestAnimationFrame(step);
  return () => cancelAnimationFrame(raf);
}
