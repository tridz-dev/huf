/**
 * Text mixed with data chips <-> the graph-IR Value it is stored as (FIELD_CONTRACT section 2). The person sees
 * "Hi [Customer name . New order]"; the flow stores one of
 *   - a plain string                                  (text only; braces are just braces),
 *   - `{"$from": "n1.customer.name"}`                 (the whole value is one chip),
 *   - `{"$template": "Hi {customer_name}", "vars": {"customer_name": {"$from": "..."}}}` (text and chips mixed;
 *     a typed `{` or `}` is written `{{` / `}}`, so typed text can never be mistaken for a placeholder).
 *
 * `parseValue` and `serializeValue` are inverses: for every stored form the engine accepts,
 * `serializeValue(parseValue(v))` deep-equals `v`. A variable that is not a plain reference (a nested template, a literal), a
 * placeholder with no variable, and variables the text never mentions are kept verbatim, never dropped or rewritten.
 */
import type { PickMode } from './types';

export interface Chip {
  /** Identifies the chip while editing only; never stored. */
  id: string;
  /** Template variable name. Starts with `table_` / `joined_` / `count_` when `mode` is set (the engine reads the prefix). */
  name: string;
  /** Reference path. Empty for an opaque or unbound chip. */
  ref: string;
  mode?: PickMode;
  /** A variable that is not a plain `$from`: kept as it was. */
  raw?: unknown;
  /** `{name}` in the text with no variable behind it (an unfinished template). */
  unbound?: boolean;
}

export type Segment = { kind: 'text'; text: string } | { kind: 'chip'; chip: Chip };

export type ValueForm = 'text' | 'from' | 'template' | 'other';

export interface ParsedValue {
  segments: Segment[];
  /** Variables the text never mentions: carried along untouched. */
  extraVars: Record<string, unknown>;
  form: ValueForm;
  /** The stored template had a `vars` key (even an empty one). */
  hadVars: boolean;
  /** Set when `form` is `other` (a number, a list, an object): the value itself. */
  other?: unknown;
}

export const MODE_PREFIX: Record<PickMode, string> = { summary: 'table_', joined: 'joined_', count: 'count_' };

const TOKEN = /\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}|[{}]/g;
/** The reference grammar of FIELD_CONTRACT: a root, then `.name` or `[n]`. */
export const REF_PATTERN = /^(input|trigger|row|foreach\.(?:item|index)|[A-Za-z_][A-Za-z0-9_]*)(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*$/;

export const isValidRef = (ref: unknown): ref is string => typeof ref === 'string' && REF_PATTERN.test(ref);

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

let counter = 0;
export const newChipId = () => `chip-${++counter}`;

export function modeOfName(name: string): PickMode | undefined {
  return (Object.keys(MODE_PREFIX) as PickMode[]).find((m) => name.startsWith(MODE_PREFIX[m]));
}

/** A short snake_case name safe as a template variable. */
export function variableName(label: string, mode?: PickMode): string {
  const base = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  const stem = /^[a-z]/.test(base) ? base : base ? `v_${base}` : 'data';
  return `${mode ? MODE_PREFIX[mode] : ''}${stem}`.slice(0, 40);
}

export function makeChip(ref: string, label: string, mode?: PickMode): Chip {
  return { id: newChipId(), name: variableName(label, mode), ref, mode };
}

const isPlainFrom = (v: unknown): v is { $from: string } => isObj(v) && Object.keys(v).length === 1 && typeof v.$from === 'string';

/** Chip names in use, so a new chip gets one nothing else has. */
export function uniqueVariable(name: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  if (!used.has(name)) return name;
  for (let i = 2; ; i++) if (!used.has(`${name}_${i}`)) return `${name}_${i}`;
}

export function parseValue(value: unknown): ParsedValue {
  if (value === undefined || value === null || value === '') return { segments: [], extraVars: {}, form: 'text', hadVars: false };
  if (typeof value === 'string') return { segments: [{ kind: 'text', text: value }], extraVars: {}, form: 'text', hadVars: false };
  if (isPlainFrom(value)) {
    const name = variableName(lastWord(value.$from));
    return { segments: [{ kind: 'chip', chip: { id: newChipId(), name, ref: value.$from } }], extraVars: {}, form: 'from', hadVars: false };
  }
  if (isObj(value) && typeof value.$template === 'string' && Object.keys(value).every((k) => k === '$template' || k === 'vars')) {
    const vars = isObj(value.vars) ? value.vars : {};
    const used = new Set<string>();
    const segments: Segment[] = [];
    let text = '';
    let last = 0;
    const flush = () => {
      if (text) segments.push({ kind: 'text', text });
      text = '';
    };
    for (const m of value.$template.matchAll(TOKEN)) {
      text += value.$template.slice(last, m.index);
      last = (m.index ?? 0) + m[0].length;
      if (m[0] === '{{') text += '{';
      else if (m[0] === '}}') text += '}';
      else if (m[1] === undefined) text += m[0];
      else {
        flush();
        const name = m[1];
        used.add(name);
        const v = vars[name];
        const base = { id: newChipId(), name, mode: modeOfName(name) };
        if (!(name in vars)) segments.push({ kind: 'chip', chip: { ...base, ref: '', mode: undefined, unbound: true } });
        else if (isPlainFrom(v)) segments.push({ kind: 'chip', chip: { ...base, ref: v.$from } });
        else segments.push({ kind: 'chip', chip: { ...base, ref: '', mode: undefined, raw: v } });
      }
    }
    text += value.$template.slice(last);
    flush();
    const extraVars = Object.fromEntries(Object.entries(vars).filter(([k]) => !used.has(k)));
    return { segments, extraVars, form: 'template', hadVars: 'vars' in value };
  }
  return { segments: [], extraVars: {}, form: 'other', hadVars: false, other: value };
}

function lastWord(ref: string): string {
  const parts = ref.replace(/\[\d+\]/g, '').split('.');
  return parts[parts.length - 1] || 'data';
}

/** Adjacent text joined, empty text dropped. */
export function normalize(segments: Segment[]): Segment[] {
  const out: Segment[] = [];
  for (const s of segments) {
    if (s.kind === 'text') {
      if (!s.text) continue;
      const prev = out[out.length - 1];
      if (prev && prev.kind === 'text') out[out.length - 1] = { kind: 'text', text: prev.text + s.text };
      else out.push(s);
    } else out.push(s);
  }
  return out;
}

const escapeBraces = (t: string) => t.replace(/\{/g, '{{').replace(/\}/g, '}}');
export const plainText = (segments: Segment[]) => segments.map((s) => (s.kind === 'text' ? s.text : '')).join('');

export interface SerializeOptions {
  /** `number`: text that is only a number is stored as a number. */
  kind?: 'number' | 'text';
}

export function serializeValue(parsed: Pick<ParsedValue, 'segments'> & Partial<ParsedValue>, opts: SerializeOptions = {}): unknown {
  if (parsed.form === 'other') return parsed.other;
  const segs = normalize(parsed.segments);
  const extra = parsed.extraVars ?? {};
  const chips = segs.flatMap((s) => (s.kind === 'chip' ? [s.chip] : []));
  const keepTemplate = parsed.form === 'template';
  if (chips.length === 0 && Object.keys(extra).length === 0 && !keepTemplate) {
    const text = plainText(segs);
    if (opts.kind === 'number' && text.trim() !== '' && Number.isFinite(Number(text))) return Number(text);
    return text;
  }
  const only = chips[0];
  if (chips.length === 1 && segs.length === 1 && Object.keys(extra).length === 0 && !keepTemplate && only.ref && !only.mode && only.raw === undefined && !only.unbound) {
    return { $from: only.ref };
  }
  // A template. Two chips that share a name but read different things get different names.
  const vars: Record<string, unknown> = {};
  const owner = new Map<string, string>();
  const nameFor = new Map<string, string>();
  for (const c of chips) {
    const key = c.unbound ? `?${c.name}` : c.raw !== undefined ? `raw:${c.name}:${JSON.stringify(c.raw)}` : `${c.ref}|${c.name}`;
    if (nameFor.has(key)) continue;
    let name = c.name;
    while (owner.has(name) && owner.get(name) !== key) name = uniqueVariable(c.name, owner.keys());
    owner.set(name, key);
    nameFor.set(key, name);
    if (c.unbound) continue;
    vars[name] = c.raw !== undefined ? c.raw : { $from: c.ref };
  }
  for (const [k, v] of Object.entries(extra)) if (!(k in vars)) vars[k] = v;
  const template = segs
    .map((s) => {
      if (s.kind === 'text') return escapeBraces(s.text);
      const c = s.chip;
      const key = c.unbound ? `?${c.name}` : c.raw !== undefined ? `raw:${c.name}:${JSON.stringify(c.raw)}` : `${c.ref}|${c.name}`;
      return `{${nameFor.get(key)}}`;
    })
    .join('');
  const out: Record<string, unknown> = { $template: template };
  if (Object.keys(vars).length > 0 || parsed.hadVars) out.vars = vars;
  return out;
}

// ---- edits on the segment list (positions count one per typed character and one per chip) ----

export function lengthOf(segments: Segment[]): number {
  return segments.reduce((n, s) => n + (s.kind === 'text' ? s.text.length : 1), 0);
}

/** Put `chip` at `pos`, splitting the text there. */
export function insertChip(segments: Segment[], pos: number, chip: Chip): Segment[] {
  const out: Segment[] = [];
  let at = 0;
  let placed = false;
  for (const s of segments) {
    if (placed) {
      out.push(s);
      continue;
    }
    const size = s.kind === 'text' ? s.text.length : 1;
    if (s.kind === 'text' && pos > at && pos < at + size) {
      out.push({ kind: 'text', text: s.text.slice(0, pos - at) }, { kind: 'chip', chip }, { kind: 'text', text: s.text.slice(pos - at) });
      placed = true;
    } else if (pos <= at) {
      out.push({ kind: 'chip', chip }, s);
      placed = true;
    } else out.push(s);
    at += size;
  }
  if (!placed) out.push({ kind: 'chip', chip });
  return normalize(out);
}

export function removeChip(segments: Segment[], id: string): Segment[] {
  return normalize(segments.filter((s) => !(s.kind === 'chip' && s.chip.id === id)));
}

/** The chip's place in the position count. */
export function positionOf(segments: Segment[], id: string): number {
  let at = 0;
  for (const s of segments) {
    if (s.kind === 'chip' && s.chip.id === id) return at;
    at += s.kind === 'text' ? s.text.length : 1;
  }
  return -1;
}

export function replaceChip(segments: Segment[], id: string, next: Chip): Segment[] {
  return segments.map((s) => (s.kind === 'chip' && s.chip.id === id ? { kind: 'chip', chip: { ...next, id } } : s));
}

/** The chip just before `pos`, if the character there is a chip. */
export function chipBefore(segments: Segment[], pos: number): Chip | null {
  let at = 0;
  for (const s of segments) {
    if (s.kind === 'chip') {
      if (at === pos - 1) return s.chip;
      at += 1;
    } else at += s.text.length;
  }
  return null;
}

export function chipAfter(segments: Segment[], pos: number): Chip | null {
  let at = 0;
  for (const s of segments) {
    if (s.kind === 'chip') {
      if (at === pos) return s.chip;
      at += 1;
    } else at += s.text.length;
  }
  return null;
}

/** Variable names already used by chips (for new, unique names). */
export const chipNames = (segments: Segment[]): string[] => segments.flatMap((s) => (s.kind === 'chip' ? [s.chip.name] : []));
