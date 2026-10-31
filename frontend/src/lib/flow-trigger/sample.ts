/**
 * The sample request a webhook trigger remembers (`node._sample`): what it is, how it is trimmed and how its fields are
 * listed for people. Mirrors huf/ai/flow/support/trigger_sample.py: secrets hidden, long text shortened, <= 8 KB.
 */
export const MAX_SAMPLE_BYTES = 8 * 1024;
const MAX_DEPTH = 6;
const MAX_TEXT = 200;
const MAX_LIST = 20;
/** Tried in order until the sample fits: (items kept per list, characters kept per text). 20 items are kept whenever they fit. */
const LIMITS: Array<[number, number]> = [[MAX_LIST, MAX_TEXT], [10, 120], [5, 80]];
const MAX_KEYS = 40;
const SECRET_KEY = /pass(word|wd)?|secret|token|authorization|api[_-]?key|credential|cookie|signature|private/i;
export const MASK = '(hidden)';

/** What the example request and the "paste a sample" box start with, so nobody faces an empty box. */
export const EXAMPLE_REQUEST = { name: 'Ada Lovelace', email: 'ada@example.com', amount: 120 };

function trim(value: unknown, depth: number, maxList = MAX_LIST, maxText = MAX_TEXT): unknown {
  if (depth > MAX_DEPTH) return '...';
  if (Array.isArray(value)) return value.slice(0, maxList).map((v) => trim(v, depth + 1, maxList, maxText));
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    Object.entries(value as Record<string, unknown>)
      .slice(0, MAX_KEYS)
      .forEach(([k, v]) => {
        out[k] = SECRET_KEY.test(k) ? MASK : trim(v, depth + 1, maxList, maxText);
      });
    return out;
  }
  if (typeof value === 'string') return value.length <= maxText ? value : `${value.slice(0, maxText - 3)}...`;
  if (value === null || typeof value === 'number' || typeof value === 'boolean') return value;
  return String(value).slice(0, maxText);
}

const size = (v: unknown) => new TextEncoder().encode(JSON.stringify(v)).length;

/** A safe, small copy of a request body. */
export function redactSample(value: unknown): unknown {
  let trimmed: unknown = null;
  for (const [maxList, maxText] of LIMITS) {
    trimmed = trim(value, 0, maxList, maxText);
    if (size(trimmed) <= MAX_SAMPLE_BYTES) return trimmed;
  }
  if (trimmed && typeof trimmed === 'object' && !Array.isArray(trimmed)) {
    const kept: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(trimmed as Record<string, unknown>)) {
      if (size({ ...kept, [k]: v }) > MAX_SAMPLE_BYTES) break;
      kept[k] = v;
    }
    return kept;
  }
  return String(trimmed).slice(0, MAX_TEXT);
}

/** Parse pasted text into a sample: an object (a bare list or value is wrapped), or null when it is not JSON. */
export function parseSampleText(text: string): Record<string, unknown> | null {
  try {
    const v = JSON.parse(text);
    if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>;
    return { value: v };
  } catch {
    return null;
  }
}

export interface SampleField {
  /** Friendly name: "Customer name", "Address > City". */
  label: string;
  /** Short readable example value. */
  example: string;
}

const humanize = (key: string) => {
  const words = key.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_\-.]+/g, ' ').trim().toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : key;
};

function show(value: unknown): string {
  if (value === null) return 'empty';
  if (typeof value === 'string') return value.length > 40 ? `${value.slice(0, 37)}...` : value || 'empty';
  return String(value);
}

/** The fields a sample offers to later steps, in plain words (no code-style paths). */
export function inferFields(sample: unknown, prefix = '', depth = 0): SampleField[] {
  if (!sample || typeof sample !== 'object' || Array.isArray(sample) || depth > 2) return [];
  const out: SampleField[] = [];
  for (const [key, value] of Object.entries(sample as Record<string, unknown>)) {
    const label = `${prefix}${humanize(key)}`;
    if (Array.isArray(value)) out.push({ label, example: value.length === 1 ? '1 item' : `${value.length} items` });
    else if (value && typeof value === 'object') {
      const inner = inferFields(value, `${label} > `, depth + 1);
      out.push(...(inner.length ? inner : [{ label, example: 'details' }]));
    } else out.push({ label, example: show(value) });
  }
  return out;
}
