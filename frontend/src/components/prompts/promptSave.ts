import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { AgentPromptDoc } from '@/services/agentPromptApi';

export interface SavePromptResult {
  name: string;
  version: number;
  /** True when the save created a new version row. */
  versioned: boolean;
  changed: boolean;
}

/**
 * Save an existing prompt from the form. The server creates the next version
 * when the body changed, updates metadata in place otherwise, and does nothing
 * for an unchanged save.
 */
export async function savePrompt(
  name: string,
  values: Partial<AgentPromptDoc>,
  options: { summary?: boolean } = {}
): Promise<SavePromptResult> {
  try {
    const response = await call.post('huf.ai.prompts.api.save_prompt', {
      prompt_name: name,
      values,
      summary: options.summary ? 1 : 0,
    });
    return response?.message as SavePromptResult;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

const HUF_PATH_PREFIX = '/huf/';

export function isInternalPath(path: string): boolean {
  try {
    const url = new URL(path, window.location.origin);
    // Reject absolute URLs, protocol-relative URLs, and different origins.
    if (url.origin !== window.location.origin) return false;
    // Reject dangerous schemes.
    if (!['http:', 'https:'].includes(url.protocol)) return false;
    // Strip javascript: / data: even if encoded.
    const decoded = decodeURIComponent(path);
    if (/^(javascript|data|vbscript):/i.test(decoded)) return false;
    // Allow only paths under the Huf app prefix. `new URL` normalizes `..` so
    // paths like /huf/agents/../../evil are rejected.
    return url.pathname.startsWith(HUF_PATH_PREFIX);
  } catch {
    return false;
  }
}

type ReturnState = { returnTo?: string; selectedPromptField?: string } | null;

/**
 * Where to go after a save when the prompt form was opened from another page
 * (for example the agent form). Returns null when there is nowhere to return to.
 */
export function readPromptReturn(state: ReturnState): { returnTo: string; selectedPromptField?: string } | null {
  let fallback: ReturnState = null;
  try {
    const raw = localStorage.getItem('agentPromptCreateReturnTo');
    fallback = raw ? (JSON.parse(raw) as ReturnState) : null;
  } catch {
    fallback = null;
  }
  const returnTo = state?.returnTo || fallback?.returnTo;
  if (!returnTo || !isInternalPath(returnTo)) return null;
  return { returnTo, selectedPromptField: state?.selectedPromptField || fallback?.selectedPromptField };
}

export function clearPromptReturn(): void {
  try {
    localStorage.removeItem('agentPromptCreateReturnTo');
  } catch {
    // ignore
  }
}
