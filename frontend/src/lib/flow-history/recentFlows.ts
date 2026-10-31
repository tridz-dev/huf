/** The flows opened most recently on this browser, newest first, for the Cmd+K palette. Kept in localStorage (best effort). */
export const RECENT_FLOWS_KEY = 'huf.flow.recent.v1';
export const RECENT_FLOWS_LIMIT = 6;

export function readRecentFlows(): string[] {
  try {
    const raw = typeof localStorage === 'undefined' ? null : localStorage.getItem(RECENT_FLOWS_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string').slice(0, RECENT_FLOWS_LIMIT) : [];
  } catch {
    return [];
  }
}

export function pushRecentFlow(flowId: string): string[] {
  const next = [flowId, ...readRecentFlows().filter((id) => id !== flowId)].slice(0, RECENT_FLOWS_LIMIT);
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(RECENT_FLOWS_KEY, JSON.stringify(next));
  } catch {
    // Private mode or blocked storage: the palette simply has no recent flows.
  }
  return next;
}
