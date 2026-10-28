import { formatAbsoluteTime, parseServerDate } from '@/lib/serverTime';

const DECISION_WORDS: Record<string, string> = { approved: 'Approved', rejected: 'Rejected', timeout: 'Timed out' };

/**
 * One-line, plain wording for an approval step's recorded decision, e.g. "Approved by ana@x.com on Oct 28, 2026, 7:15 AM".
 * Reads the engine's `decision` / `decided_by` / `decided_at` keys; returns null for any other step output.
 */
export function describeDecision(output: unknown): string | null {
    if (!output || typeof output !== 'object') return null;
    const o = output as { decision?: unknown; decided_by?: unknown; decided_at?: unknown };
    if (typeof o.decision !== 'string' || !(o.decision in DECISION_WORDS)) return null;
    const word = DECISION_WORDS[o.decision];
    if (o.decision === 'timeout') return `${word} with no answer`;
    const by = typeof o.decided_by === 'string' && o.decided_by ? ` by ${o.decided_by}` : '';
    const at = typeof o.decided_at === 'string' && parseServerDate(o.decided_at) ? ` on ${formatAbsoluteTime(o.decided_at)}` : '';
    return `${word}${by}${at}`;
}

/** Output keys that hold the id of another step (router choice, condition branch, approval next/timeout target). */
const NODE_ID_KEYS = new Set(['node_id', 'next_node_id', 'next', 'on_true', 'on_false', 'timeout_next', 'resume_node', 'target']);

/**
 * Copy of a step output where every value that points at another step shows that step's title instead of its id.
 * `titleOf` returns the title for a known step id and null for any other string, which stays as it is.
 */
export function titleNodeIds(value: unknown, titleOf: (id: string) => string | null): unknown {
    if (Array.isArray(value)) return value.map((v) => titleNodeIds(v, titleOf));
    if (!value || typeof value !== 'object') return value;
    return Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([k, v]) => [
            k,
            NODE_ID_KEYS.has(k) && typeof v === 'string' ? (titleOf(v) ?? v) : titleNodeIds(v, titleOf),
        ]),
    );
}

/** A step result the engine recorded as failed: `{status: 'failed', error}`, or a tool result with `success: false`. */
export function isFailedStepOutput(output: unknown): boolean {
    if (!output || typeof output !== 'object') return false;
    const o = output as { status?: unknown; success?: unknown; error?: unknown };
    return o.status === 'failed' || o.success === false || (typeof o.error === 'string' && o.error !== '' && o.status !== 'success');
}

/** The output without the `status` / `error` keys a failed step card already shows as its reason. */
export function withoutFailureKeys(output: unknown): unknown {
    if (!output || typeof output !== 'object' || Array.isArray(output)) return output;
    return Object.fromEntries(Object.entries(output as Record<string, unknown>).filter(([k]) => k !== 'status' && k !== 'error'));
}
