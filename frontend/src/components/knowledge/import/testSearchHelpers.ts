/** Helpers for the Test a question panel: result shape, match labels, highlighting. */

export interface TestResult {
  text?: string;
  title?: string;
  score?: number;
  chunk_id?: string;
  input_id?: string | null;
  input_title?: string | null;
  metadata?: Record<string, unknown> | null;
}

export type MatchLevel = 'high' | 'good' | 'weak';

export const MATCH_LABEL: Record<MatchLevel, string> = {
  high: 'High match',
  good: 'Good match',
  weak: 'Weak match',
};

export function normalizeResults(raw: unknown): TestResult[] {
  if (Array.isArray(raw)) return raw as TestResult[];
  const obj = raw as { results?: unknown } | null;
  return obj && Array.isArray(obj.results) ? (obj.results as TestResult[]) : [];
}

/**
 * Score scales differ by search method: vector/hybrid scores are similarity values
 * in 0..1, keyword (BM25) scores are open-ended. So:
 *  - when every score is within 0..1: absolute (>=0.75 high, >=0.5 good, else weak)
 *  - otherwise: relative to the best result (>=0.8 high, >=0.5 good, else weak)
 * The raw score is always shown in the tooltip.
 */
export function matchLevels(results: TestResult[]): MatchLevel[] {
  const scores = results.map((r) => (typeof r.score === 'number' ? r.score : 0));
  const top = Math.max(0, ...scores);
  const bounded = top <= 1 \&\& top >= 0.5; // weak-looking bounded scores are keyword scores: use relative
  return scores.map((s) => {
    const v = bounded ? s : top > 0 ? s / top : 0;
    const [hi, good] = bounded ? [0.75, 0.5] : [0.8, 0.5];
    return v >= hi ? 'high' : v >= good ? 'good' : 'weak';
  });
}

/** Citation location, e.g. "page 3" or "passage 2". */
export function locationOf(r: TestResult): string {
  const m = r.metadata ?? {};
  const page = m.page ?? m.page_number;
  if (page != null && page !== '') return `page ${String(page)}`;
  const idx = Number(m.chunk_index);
  return Number.isFinite(idx) ? `passage ${idx + 1}` : '';
}

/** Split text into parts, flagging pieces that match a query word (3+ letters). */
export function highlightParts(text: string, query: string): { text: string; hit: boolean }[] {
  const words = Array.from(new Set(query.toLowerCase().split(/\W+/).filter((w) => w.length >= 3)));
  if (!words.length) return [{ text, hit: false }];
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
  return text
    .split(re)
    .filter(Boolean)
    .map((part) => ({ text: part, hit: words.includes(part.toLowerCase()) }));
}
