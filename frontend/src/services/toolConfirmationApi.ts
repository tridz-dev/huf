import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/** Frozen N06 contract: huf/ai/tool_confirmation.py (see N06_CONTRACT.md). */
export type ToolConfirmationState =
  | 'pending'
  | 'approved'
  | 'denied'
  | 'expired'
  | 'executed'
  | 'failed';

export interface ToolConfirmationSummary {
  action: string | null;
  recipient_count: number | null;
  template: string | null;
  channel: string | null;
  sample: string | null;
}

export interface ToolConfirmation {
  type: 'confirmation_request';
  id: string;
  tool: string;
  state: ToolConfirmationState;
  summary: ToolConfirmationSummary;
  /** ISO-8601 UTC with offset (legacy naive `YYYY-MM-DD HH:MM:SS` is read as UTC). */
  expires_at: string | null;
  conversation?: string | null;
  error?: string | null;
}

export interface DecideResult {
  confirmation: ToolConfirmation;
  result: unknown;
}

export type ToolConfirmationErrorCode =
  | 'not_found'
  | 'forbidden'
  | 'expired'
  | 'already_decided'
  | 'args_changed'
  | 'role_denied'
  | 'execution_failed';

const ERROR_RE = /confirmation_(not_found|forbidden|expired|already_decided|args_changed|role_denied|execution_failed)/;

/** Stable error code from a thrown Frappe error, or null. */
export function getConfirmationErrorCode(error: unknown): ToolConfirmationErrorCode | null {
  const parts: string[] = [];
  const seen = new Set<unknown>();
  const visit = (e: unknown, depth = 0) => {
    if (e == null || depth > 3 || seen.has(e)) return;
    seen.add(e);
    if (typeof e === 'string') {
      parts.push(e);
    } else if (typeof e === 'object') {
      for (const v of Object.values(e as Record<string, unknown>)) visit(v, depth + 1);
      if (e instanceof Error) parts.push(e.message);
    }
  };
  visit(error);
  const m = ERROR_RE.exec(parts.join(' '));
  return m ? (m[1] as ToolConfirmationErrorCode) : null;
}

export const CONFIRMATION_ERROR_MESSAGES: Record<ToolConfirmationErrorCode, string> = {
  not_found: 'This approval request no longer exists.',
  forbidden: 'Only the person who requested this action can approve or deny it.',
  expired: 'This approval request expired. Ask the agent to try again.',
  already_decided: 'This request was already decided.',
  args_changed: 'The request changed after it was created, so it was not run. Ask the agent to try again.',
  role_denied: 'You no longer have permission to perform this action.',
  execution_failed: 'The action was approved but failed to run.',
};

export function confirmationErrorMessage(error: unknown): string {
  const code = getConfirmationErrorCode(error);
  return code ? CONFIRMATION_ERROR_MESSAGES[code] : 'Could not record your decision. Please try again.';
}

/**
 * Parse `expires_at` to an absolute epoch-ms instant. ISO-8601 with an offset
 * (or Z) is used as-is; a legacy naive `YYYY-MM-DD HH:MM:SS` is treated as UTC
 * (never device-local, so the countdown does not drift with device timezone).
 */
export function parseExpiresAt(value: string | null | undefined): number | null {
  if (!value) return null;
  let v = value.trim().replace(' ', 'T');
  if (!/(Z|[+-]\d{2}(:?\d{2})?)$/i.test(v.replace(/^\d{4}-\d{2}-\d{2}/, ''))) v += 'Z';
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : t;
}

/** Pull a `confirmation_request` object out of tool-result text (plain JSON or JSON embedded in text). */
export function parseConfirmationRequest(raw: unknown): ToolConfirmation | null {
  const text = typeof raw === 'string' ? raw : null;
  if (!text || !text.includes('confirmation_request')) return null;
  const tryParse = (s: string): ToolConfirmation | null => {
    try {
      const o = JSON.parse(s);
      return o && o.type === 'confirmation_request' && typeof o.id === 'string' ? normalize(o) : null;
    } catch {
      return null;
    }
  };
  const whole = tryParse(text.trim());
  if (whole) return whole;
  // Embedded: scan balanced braces from each '{' preceding the marker.
  let from = 0;
  for (;;) {
    const start = text.indexOf('{', from);
    if (start < 0) return null;
    let depth = 0;
    let inStr = false;
    for (let i = start; i < text.length; i++) {
      const c = text[i];
      if (inStr) {
        if (c === '\\') i++;
        else if (c === '"') inStr = false;
      } else if (c === '"') inStr = true;
      else if (c === '{') depth++;
      else if (c === '}' && --depth === 0) {
        const parsed = tryParse(text.slice(start, i + 1));
        if (parsed) return parsed;
        break;
      }
    }
    from = start + 1;
  }
}

/** Keep only contract fields (never carry through args/OTP/etc.). */
export function normalize(o: Record<string, any>): ToolConfirmation { // eslint-disable-line @typescript-eslint/no-explicit-any
  const s = o.summary ?? {};
  return {
    type: 'confirmation_request',
    id: String(o.id),
    tool: String(o.tool ?? ''),
    state: (o.state ?? 'pending') as ToolConfirmationState,
    summary: {
      action: s.action ?? null,
      recipient_count: s.recipient_count ?? null,
      template: s.template ?? null,
      channel: s.channel ?? null,
      sample: s.sample ?? null,
    },
    expires_at: o.expires_at ?? null,
    conversation: o.conversation ?? null,
    error: o.error ?? null,
  };
}

export async function getPendingConfirmations(conversation?: string | null): Promise<ToolConfirmation[]> {
  try {
    const result = await call.post('huf.ai.tool_confirmation.get_pending', {
      conversation: conversation ?? undefined,
    });
    const list = (result.message?.confirmations ?? []) as Record<string, unknown>[];
    return list.map((c) => normalize(c));
  } catch (error) {
    handleFrappeError(error, 'Error loading pending approvals');
  }
}

export async function decideConfirmation(id: string, approve: boolean): Promise<DecideResult> {
  try {
    const result = await call.post('huf.ai.tool_confirmation.decide', { id, approve: approve ? 1 : 0 });
    const msg = result.message as { confirmation: Record<string, unknown>; result: unknown };
    return { confirmation: normalize(msg.confirmation), result: msg.result ?? null };
  } catch (error) {
    handleFrappeError(error, 'Error recording approval decision');
  }
}
