/**
 * Two step fields keep their words in a plain string, not in a `{$template}` value, but people fill them in with
 * the same "Use data" chips as everywhere else:
 *
 *  - a message or question with `{input.customer.name}` placeholders (the approval message and title, the router's
 *    question); the engine fills them in with `render_text_refs`. `{table:x}`, `{joined:x}` and `{count:x}` ask
 *    for a list or a record in a particular wording (the same three choices the picker offers elsewhere);
 *  - an agent's prompt with `{name}` placeholders and a separate `prompt_bindings` object (`render_agent_prompt`).
 *
 * These helpers turn the stored string into the value `DataInput` shows (and back) without changing what is stored for a
 * flow nobody edits: `fromTextRefs(toTextRefs(text)) === text` for every text the engine accepts.
 */
import { modeOfName, variableName } from './chips';
import type { PickMode } from './types';

const REF_TAIL = '[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*|\\[\\d+\\])*';
/** The engine's placeholder (`router_text._TEXT_REF_RE`), with the optional wording prefix. */
const PLACEHOLDER = new RegExp(`(?<!\\{)\\{(?:(table|joined|count):)?(${REF_TAIL})\\}(?!\\})`, 'g');
const PREFIX_OF_MODE: Record<PickMode, string> = { summary: 'table', joined: 'joined', count: 'count' };
const MODE_OF_PREFIX: Record<string, PickMode> = { table: 'summary', joined: 'joined', count: 'count' };

const escapeBraces = (t: string) => t.replace(/\{/g, '{{').replace(/\}/g, '}}');
const lastWord = (ref: string) => ref.replace(/\[\d+\]/g, '').split('.').pop() || 'data';

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

/** The stored message as the value the chip input shows: plain text, or a template with one variable per placeholder. */
export function toTextRefs(text: unknown): unknown {
  if (typeof text !== 'string' || text === '') return text ?? '';
  const matches = [...text.matchAll(PLACEHOLDER)];
  if (matches.length === 0) return text;
  const vars: Record<string, unknown> = {};
  const names = new Map<string, string>();
  let template = '';
  let last = 0;
  for (const m of matches) {
    template += escapeBraces(text.slice(last, m.index));
    last = (m.index ?? 0) + m[0].length;
    const mode = m[1] ? MODE_OF_PREFIX[m[1]] : undefined;
    const key = `${m[1] ?? ''}:${m[2]}`;
    let name = names.get(key);
    if (!name) {
      const base = variableName(lastWord(m[2]), mode);
      name = base;
      for (let i = 2; name in vars; i++) name = `${base}_${i}`;
      names.set(key, name);
      vars[name] = { $from: m[2] };
    }
    template += `{${name}}`;
  }
  template += escapeBraces(text.slice(last));
  return { $template: template, vars };
}

/** What the chip input produced, back as the message string. Chips become `{reference}` placeholders. */
export function fromTextRefs(value: unknown): string | undefined {
  if (value === undefined || value === null || value === '') return undefined;
  if (typeof value === 'string') return value;
  if (isObj(value) && typeof value.$from === 'string') return `{${value.$from}}`;
  if (isObj(value) && typeof value.$template === 'string') return rebuild(value.$template, isObj(value.vars) ? value.vars : {});
  return String(value);
}

function rebuild(template: string, vars: Record<string, unknown>): string {
  let out = '';
  let last = 0;
  for (const m of template.matchAll(/\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}|[{}]/g)) {
    out += template.slice(last, m.index);
    last = (m.index ?? 0) + m[0].length;
    if (m[0] === '{{') out += '{';
    else if (m[0] === '}}') out += '}';
    else if (m[1] === undefined) out += m[0];
    else {
      const v = vars[m[1]];
      const mode = modeOfName(m[1]);
      out += isObj(v) && typeof v.$from === 'string' ? `{${mode ? `${PREFIX_OF_MODE[mode]}:` : ''}${v.$from}}` : '';
    }
  }
  return out + template.slice(last);
}

// ---- the agent's prompt: `{name}` placeholders + `prompt_bindings` ----

const TEMPLATE_TOKEN = /\{\{|\}\}|\{[A-Za-z_][A-Za-z0-9_]*\}/;

/** The agent's prompt and its bindings as the value the chip input shows. */
export function promptToValue(prompt: unknown, bindings: unknown): unknown {
  const text = typeof prompt === 'string' ? prompt : '';
  const vars = isObj(bindings) ? bindings : {};
  if (Object.keys(vars).length === 0 && !TEMPLATE_TOKEN.test(text)) return text;
  return { $template: text, vars };
}

/** What the chip input produced, back as `{prompt, prompt_bindings}`. Typed braces are kept as braces. */
export function valueToPrompt(value: unknown): { prompt: string | undefined; prompt_bindings: Record<string, unknown> | undefined } {
  if (value === undefined || value === null || value === '') return { prompt: undefined, prompt_bindings: undefined };
  if (typeof value === 'string') return { prompt: escapeBraces(value), prompt_bindings: undefined };
  if (isObj(value) && typeof value.$from === 'string') {
    const name = variableName(lastWord(value.$from));
    return { prompt: `{${name}}`, prompt_bindings: { [name]: { $from: value.$from } } };
  }
  if (isObj(value) && typeof value.$template === 'string') {
    const vars = isObj(value.vars) ? value.vars : {};
    return { prompt: value.$template, prompt_bindings: Object.keys(vars).length ? vars : undefined };
  }
  return { prompt: String(value), prompt_bindings: undefined };
}
