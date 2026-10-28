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
