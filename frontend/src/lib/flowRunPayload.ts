const KEY = (flowId: string) => `huf.flow.lastRunPayload.${flowId}`;

/** The payload last used to run this flow in this browser, or `{}`. */
export function readLastPayload(flowId: string): string {
  try {
    return window.localStorage.getItem(KEY(flowId)) || '{}';
  } catch {
    return '{}';
  }
}

export function rememberPayload(flowId: string, text: string): void {
  try {
    window.localStorage.setItem(KEY(flowId), text);
  } catch {
    /* private mode: nothing to remember */
  }
}

/** Parse the run dialog text. A blank box means `{}`; the payload must be a JSON object. */
export function parsePayload(text: string): { value: Record<string, unknown> | null; error: string | null } {
  if (!text.trim()) return { value: {}, error: null };
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { value: null, error: "This isn't valid JSON. Check for missing quotes, commas or brackets." };
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { value: null, error: 'The input must be a JSON object, like {"name": "Ada"}.' };
  }
  return { value: parsed as Record<string, unknown>, error: null };
}
