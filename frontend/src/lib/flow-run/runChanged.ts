const EVENT = 'huf:flow-run-changed';

/** Tell every open view of a run (the canvas drawing it, the run sheet) that someone just decided or resumed it, so they re-read it now. */
export function announceRunChanged(runId: string): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(EVENT, { detail: { runId } }));
}

/** Calls `fn` when `announceRunChanged` fires for `runId`; returns the unsubscribe. */
export function onRunChanged(runId: string, fn: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const handler = (e: Event) => {
    if ((e as CustomEvent<{ runId?: string }>).detail?.runId === runId) fn();
  };
  window.addEventListener(EVENT, handler);
  return () => window.removeEventListener(EVENT, handler);
}
