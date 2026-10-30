/**
 * The canvas hands moves and connections to the flow a moment (50 ms) after they happen, so a drag is one write, not a hundred.
 * Anything that rearranges the whole graph from somewhere else (Tidy layout) must see those moves first, or its result is
 * overwritten by the late write. The canvas registers how to write its pending changes now; `flushPendingWrites` runs it.
 */
let flush: (() => void) | null = null;

/** Register the canvas's "write what is pending now". Returns the way to unregister it. */
export function registerPendingFlush(fn: () => void): () => void {
  flush = fn;
  return () => {
    if (flush === fn) flush = null;
  };
}

/** Write any move or connection the canvas has not handed to the flow yet. Safe to call at any time. */
export function flushPendingWrites(): void {
  flush?.();
}
