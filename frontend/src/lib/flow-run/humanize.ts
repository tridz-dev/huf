import { formatAbsoluteTime, parseServerDate } from '@/lib/serverTime';
import { htmlToText } from '@/lib/flow-run/flowRunDoc';

/**
 * Render-time humanizing of run data (UX-2). Pure functions, no React: the HumanValue component, the
 * approvals bell and the run title all use these, so one rule set decides how data reads to a person.
 *
 * Rules (UX_NON_TECHNICAL_RULES 1, 2, 8): an object is labelled rows, a list is "N items" with each item as
 * a row, dates are local friendly time, booleans are Yes / No, empty values are hidden, long text is
 * collapsed, step ids are step titles. Nothing here ever prints JSON.
 */

const ACRONYMS = new Set(['id', 'url', 'uri', 'sku', 'api', 'ip', 'ui', 'pdf', 'csv', 'sms', 'otp', 'vat', 'gst', 'utm', 'ssn', 'html', 'json', 'xml', 'uuid', 'ai', 'crm', 'erp', 'cc', 'bcc']);

/** Keys the server adds to documents or the engine adds to its bookkeeping: they are never part of what a person entered. */
const HIDDEN_KEYS = new Set([
  'doctype', 'docstatus', 'idx', 'owner', 'creation', 'modified', 'modified_by', 'parent', 'parentfield', 'parenttype',
  'amended_from', 'naming_series', '__unsaved', '_trigger', '_user_tags', '_comments', '_assign', '_liked_by',
]);

/** Keys that name an item best, used as the heading of a list item card and first in a one-line sentence. */
const TITLE_KEYS = ['name', 'title', 'label', 'subject', 'customer', 'customer_name', 'full_name', 'description'];
const FACT_KEYS = ['name', 'title', 'label', 'subject', 'customer', 'customer_name', 'full_name', 'amount', 'total', 'grand_total', 'price', 'status', 'state', 'email', 'description'];

/** Keys whose numeric value is an identifier or a year: never grouped with thousands separators. */
const PLAIN_NUMBER_KEY = /(^|_)(id|code|number|no|phone|zip|postcode|year|pin)$/i;

const ISO = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_IN_TEXT = /\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?\b/g;
const NODE_ID = /^node_\d{6,}$/;

export const LONG_TEXT_CHARS = 120;
export const LONG_TEXT_LINES = 3;

/** Names and labels that sharpen the output: step titles for ids, field labels from a schema. */
export interface HumanOptions {
  /** Id -> display name (steps, users). A string value that equals an id is shown as the name. */
  names?: Record<string, string>;
  /** Field key (or dotted path) -> label from a schema or doctype. */
  labels?: Record<string, string>;
  /** Extra keys to leave out (at every depth). */
  hideKeys?: readonly string[];
}

export type HumanNode =
  | { kind: 'empty' }
  | { kind: 'scalar'; text: string }
  | { kind: 'text'; text: string; preview: string; long: boolean }
  | { kind: 'rows'; rows: HumanRow[] }
  | { kind: 'list'; count: number; summary: string; items: HumanItem[] };

export interface HumanRow {
  key: string;
  /** Dotted path from the root, used for stable test ids. */
  path: string;
  label: string;
  node: HumanNode;
}

export interface HumanItem {
  index: number;
  /** "Ada Lovelace" for an object that has a name-like field, else "Item 2". */
  title: string;
  /** Short facts shown while the item is closed ("Total 450, Paid"). */
  facts: string;
  node: HumanNode;
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

/** "customer_name" -> "Customer Name", "orderID" -> "Order ID". A schema/doctype title wins. */
export function labelFor(key: string, title?: string | null): string {
  if (title && title.trim()) return title.trim();
  const words = key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_\-.]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return key;
  return words
    .map((w) => (ACRONYMS.has(w.toLowerCase()) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()))
    .join(' ');
}

export function isIsoDate(value: string): boolean {
  return ISO.test(value.trim());
}

/** "Oct 29, 2026" for a plain date, "Oct 29, 2026, 5:15 PM" for a date and time (in the browser's zone); the text itself when it is not a date. */
export function friendlyDate(value: string): string {
  const text = value.trim();
  const d = DATE_ONLY.exec(text);
  if (d) {
    const date = new Date(Number(d[1]), Number(d[2]) - 1, Number(d[3]));
    return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { dateStyle: 'medium' });
  }
  if (!parseServerDate(text)) return value;
  return formatAbsoluteTime(text) || value;
}

/** Number as people read it: 12345 -> "12,345"; ids, codes and years are left alone. */
function friendlyNumber(n: number, key: string): string {
  if (!Number.isFinite(n)) return String(n);
  if (PLAIN_NUMBER_KEY.test(key) || (Number.isInteger(n) && Math.abs(n) < 10000)) return String(n);
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function cut(text: string, max: number): string {
  if (text.length <= max) return text;
  const slice = text.slice(0, max);
  const space = slice.lastIndexOf(' ');
  return `${(space > max * 0.6 ? slice.slice(0, space) : slice).trimEnd()}…`;
}

function countWord(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** A string that is really a JSON object or list (tool results are often stored that way): its parsed value, else undefined. */
function parseJsonString(text: string): unknown {
  const t = text.trim();
  if (!((t.startsWith('{') && t.endsWith('}')) || (t.startsWith('[') && t.endsWith(']')))) return undefined;
  try {
    const parsed = JSON.parse(t);
    return parsed !== null && typeof parsed === 'object' ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function scalarNode(value: unknown, key: string, opts: HumanOptions): HumanNode {
  if (value === null || value === undefined) return { kind: 'empty' };
  if (typeof value === 'boolean') return { kind: 'scalar', text: value ? 'Yes' : 'No' };
  if (typeof value === 'number') return { kind: 'scalar', text: friendlyNumber(value, key) };
  if (typeof value !== 'string') return { kind: 'scalar', text: String(value) };
  const named = opts.names?.[value];
  if (named) return { kind: 'scalar', text: named };
  if (NODE_ID.test(value)) return { kind: 'scalar', text: 'Another step' };
  if (isIsoDate(value)) return { kind: 'scalar', text: friendlyDate(value) };
  const text = htmlToText(value).trim();
  if (!text) return { kind: 'empty' };
  const lines = text.split('\n').length;
  const long = text.length > LONG_TEXT_CHARS || lines > LONG_TEXT_LINES;
  return long ? { kind: 'text', text, preview: cut(text.split('\n').slice(0, LONG_TEXT_LINES).join(' '), LONG_TEXT_CHARS), long } : { kind: 'text', text, preview: text, long };
}

/** Plain text of a node for one-line use (list summaries, bell sentences): rows as "Label: value", lists as "N items". */
export function nodeText(node: HumanNode, maxFacts = 4): string {
  switch (node.kind) {
    case 'empty': return '';
    case 'scalar': return node.text;
    case 'text': return node.long ? node.preview : node.text;
    case 'list': return countWord(node.count, 'item', 'items');
    case 'rows': return factsOf(node.rows, maxFacts);
  }
}

/** A value inside a "Label: value" fact: nested rows collapse to their values ("Customer: Ada"), a list to "3 items". */
function factValue(node: HumanNode): string {
  if (node.kind === 'rows') return node.rows.slice(0, 2).map((r) => factValue(r.node)).join(', ');
  return nodeText(node);
}

function rowRank(key: string): number {
  const i = FACT_KEYS.indexOf(key.toLowerCase());
  return i === -1 ? FACT_KEYS.length : i;
}

/** "Name: Ada, Total: 450" from the most telling rows first, "and N more" when there are others. */
function factsOf(rows: HumanRow[], max: number): string {
  const ordered = [...rows].sort((a, b) => rowRank(a.key) - rowRank(b.key));
  const shown = ordered.slice(0, max).map((r) => `${r.label}: ${factValue(r.node)}`);
  const extra = rows.length - shown.length;
  return extra > 0 ? `${shown.join(', ')} and ${extra} more` : shown.join(', ');
}

function listNode(items: unknown[], key: string, path: string, opts: HumanOptions): HumanNode {
  const nodes = items.map((v, i) => ({ i, node: toNode(v, key, `${path}.${i}`, opts) })).filter((x) => x.node.kind !== 'empty');
  if (nodes.length === 0) return { kind: 'empty' };
  const humanItems: HumanItem[] = nodes.map(({ i, node }) => {
    let title = `Item ${i + 1}`;
    let factsRows: HumanRow[] = [];
    if (node.kind === 'rows') {
      const titleRow = TITLE_KEYS.map((k) => node.rows.find((r) => r.key.toLowerCase() === k)).find((r) => r && (r.node.kind === 'text' || r.node.kind === 'scalar'));
      if (titleRow) title = nodeText(titleRow.node);
      factsRows = node.rows.filter((r) => r !== titleRow);
    }
    const facts = node.kind === 'rows' ? factsOf(factsRows, 3) : nodeText(node);
    return { index: i, title, facts, node };
  });
  const allScalar = nodes.every((n) => n.node.kind === 'scalar' || n.node.kind === 'text');
  const shownTexts = humanItems.slice(0, 3).map((it) => (allScalar ? it.facts : it.title));
  const more = humanItems.length - shownTexts.length;
  const summary = `${shownTexts.map((t) => cut(t, 40)).join(', ')}${more > 0 ? ` and ${more} more` : ''}`;
  return { kind: 'list', count: humanItems.length, summary, items: humanItems };
}

function toNode(value: unknown, key: string, path: string, opts: HumanOptions): HumanNode {
  if (typeof value === 'string') {
    const parsed = parseJsonString(value);
    if (parsed !== undefined) return toNode(parsed, key, path, opts);
  }
  if (Array.isArray(value)) return listNode(value, key, path, opts);
  if (isObj(value)) {
    const hide = opts.hideKeys;
    const rows: HumanRow[] = [];
    for (const [k, v] of Object.entries(value)) {
      if (k.startsWith('_') || HIDDEN_KEYS.has(k) || hide?.includes(k)) continue;
      const rowPath = path ? `${path}.${k}` : k;
      const node = toNode(v, k, rowPath, opts);
      if (node.kind === 'empty') continue;
      rows.push({ key: k, path: rowPath, label: labelFor(k, opts.labels?.[rowPath] ?? opts.labels?.[k]), node });
    }
    return rows.length ? { kind: 'rows', rows } : { kind: 'empty' };
  }
  return scalarNode(value, key, opts);
}

/** The display tree for any value. `{kind: 'empty'}` when there is nothing worth showing. */
export function humanize(value: unknown, opts: HumanOptions = {}): HumanNode {
  return toNode(value, '', '', opts);
}

/** One plain sentence-ish line for a value: "Customer: Ada Lovelace, Total: 450" or "3 items: A, B and 1 more". */
export function humanizeSentence(value: unknown, opts: HumanOptions = {}, maxFacts = 4): string {
  const node = humanize(value, opts);
  if (node.kind === 'list') return `${countWord(node.count, 'item', 'items')}${node.summary ? `: ${node.summary}` : ''}`;
  return nodeText(node, maxFacts);
}

/** Index just past the JSON value that starts at `start` (a `{` or `[`), or -1 when the brackets never balance. */
function endOfBalanced(text: string, start: number): number {
  const open = text[start];
  const close = open === '{' ? '}' : ']';
  let depth = 0;
  let inStr: string | null = null;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (c === '\\') i++;
      else if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'") inStr = c;
    else if (c === open) depth++;
    else if (c === close && --depth === 0) return i + 1;
  }
  return -1;
}

function parseLoose(fragment: string): unknown {
  try {
    return JSON.parse(fragment);
  } catch {
    // Python-style dict printed by an older engine: single quotes, None, True, False.
    try {
      return JSON.parse(fragment.replace(/\bNone\b/g, 'null').replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false').replace(/'/g, '"'));
    } catch {
      return undefined;
    }
  }
}

/**
 * Text written by a flow ("Approve this order: {"amount": 42, ...}") with every embedded JSON object or list
 * replaced by its plain form ("Approve this order: Amount: 42, Customer: Ada") and ISO timestamps made friendly.
 * Text without JSON comes back unchanged. Used where a sentence is expected: bell, approval message.
 */
export function humanizeMessageText(text: string, opts: HumanOptions = {}): string {
  if (!text) return text;
  let out = '';
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === '{' || c === '[') {
      const end = endOfBalanced(text, i);
      if (end > i + 1) {
        const parsed = parseLoose(text.slice(i, end));
        if (parsed !== undefined && parsed !== null && typeof parsed === 'object') {
          const plain = humanizeSentence(parsed, opts);
          out += plain || '';
          i = end;
          continue;
        }
      }
    }
    out += c;
    i++;
  }
  out = out.replace(ISO_IN_TEXT, (m) => friendlyDate(m)).replace(/[ \t]{2,}/g, ' ').replace(/\s+([.,;:!?])/g, '$1');
  return out.trim();
}

function stripEmpty(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(stripEmpty);
  if (isObj(v)) {
    return Object.fromEntries(Object.entries(v).filter(([, x]) => x !== null && x !== undefined && x !== '').map(([k, x]) => [k, stripEmpty(x)]));
  }
  return v;
}

/** Equal data once empty values are ignored: used to spot the trigger input repeated as the first step's output. */
export function sameData(a: unknown, b: unknown): boolean {
  return JSON.stringify(canonical(stripEmpty(a))) === JSON.stringify(canonical(stripEmpty(b)));
}

function canonical(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(canonical);
  if (isObj(v)) return Object.fromEntries(Object.keys(v).sort().map((k) => [k, canonical(v[k])]));
  return v;
}

const hasData = (v: unknown): boolean => humanize(v).kind !== 'empty';

/**
 * Where the trigger input is shown. `merged` puts it inside the first step ("Data received") so it is never
 * printed twice; `none` means there is no input to show; `separate` keeps its own block (the input differs
 * from every step output, e.g. data kept by the engine for later steps).
 */
export type TriggerPlacement = { mode: 'merged'; stepId: string } | { mode: 'separate' } | { mode: 'none' };

export function placeTriggerInput(input: unknown, steps: Array<{ id: string; output: unknown }>): TriggerPlacement {
  if (!hasData(input)) return { mode: 'none' };
  const first = steps[0];
  if (first && (sameData(first.output, input) || !hasData(first.output))) return { mode: 'merged', stepId: first.id };
  return { mode: 'separate' };
}

/** Who started a run, in words: the person ("you" for the viewer), or what fired it. */
export function startedByWords(args: { triggerType?: string | null; owner?: string | null; ownerName?: string | null; currentUser?: string | null }): string {
  const t = (args.triggerType || '').toLowerCase();
  if (t.includes('webhook')) return 'a webhook';
  if (t.includes('schedule')) return 'a schedule';
  if (t.includes('doc') || t.includes('data') || t.includes('event')) return 'a data change';
  if (args.owner && args.currentUser && args.owner === args.currentUser) return 'you';
  return args.ownerName || args.owner || 'someone';
}

/** "Run #12 · started by you · 2 mins ago". Parts without data are left out; never the internal run id. */
export function friendlyRunTitle(args: { runNumber?: number | null; startedBy?: string | null; ago?: string | null }): string {
  const parts = [args.runNumber ? `Run #${args.runNumber}` : 'Run'];
  if (args.startedBy) parts.push(`started by ${args.startedBy}`);
  if (args.ago) parts.push(args.ago.charAt(0).toLowerCase() + args.ago.slice(1));
  return parts.join(' · ');
}
