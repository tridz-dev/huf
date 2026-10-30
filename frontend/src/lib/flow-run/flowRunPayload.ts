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

/** How a run starts. A test run reads for real but sends nothing and changes nothing outside the flow. */
export type RunMode = 'test' | 'real';

/** What the Run buttons are called, and what the Run dialog's own button says for each mode. */
export const RUN_MODE_BUTTON: Record<RunMode, string> = { test: 'Run test', real: 'Run for real' };

/** The one place the card / header Run label is decided (`Run test`: the dialog opens with Test run chosen). */
export const RUN_BUTTON_LABEL = RUN_MODE_BUTTON.test;
