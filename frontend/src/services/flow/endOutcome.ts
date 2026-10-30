import type { EndOutcome, OutcomeTone } from '@/types/flow.types';

/** The End step's outcome as stored: only the parts that are set (`{}` means "Finished", neutral, so it is left out). */
export function cleanOutcome(raw: unknown): EndOutcome | undefined {
    if (!raw || typeof raw !== 'object') return undefined;
    const o = raw as { label?: unknown; tone?: unknown };
    const label = typeof o.label === 'string' && o.label.trim() !== '' ? o.label.trim() : undefined;
    const tone: OutcomeTone | undefined = o.tone === 'good' || o.tone === 'bad' || o.tone === 'neutral' ? o.tone : undefined;
    return label || tone ? { ...(label ? { label } : {}), ...(tone ? { tone } : {}) } : undefined;
}

/** `{outcome}` to spread into a config, or nothing when there is no outcome. */
export const endOutcomeConfig = (raw: unknown): { outcome?: EndOutcome } => {
    const outcome = cleanOutcome(raw);
    return outcome ? { outcome } : {};
};
