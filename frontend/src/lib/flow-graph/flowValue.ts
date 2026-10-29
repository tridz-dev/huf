/**
 * Helpers for graph-IR `Value` fields (graph_ir.schema.json $defs/Value): a literal, a
 * `{"$from": "a.b"}` reference, a `{"$template": "...", "vars": {...}}` template, or a
 * composed array/object. The UI edits one value in one of four modes.
 */
export type ValueMode = 'literal' | 'reference' | 'template' | 'json';

export function valueMode(v: unknown): ValueMode {
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    if ('$from' in v) return 'reference';
    if ('$template' in v) return 'template';
  }
  if (v !== null && typeof v === 'object') return 'json';
  // Numbers and booleans are not text: show them as JSON so editing keeps their type.
  if (typeof v === 'number' || typeof v === 'boolean') return 'json';
  return 'literal';
}

export interface TemplateValue {
  $template: string;
  vars?: Record<string, unknown>;
}

/** Text shown in the editor for the value's current mode. */
export function valueToText(v: unknown): string {
  switch (valueMode(v)) {
    case 'reference':
      return String((v as { $from?: unknown }).$from ?? '');
    case 'template':
      return String((v as TemplateValue).$template ?? '');
    case 'json':
      return JSON.stringify(v, null, typeof v === 'object' ? 2 : undefined);
    default:
      return v == null ? '' : String(v);
  }
}

/** Template vars as pretty JSON text ('' when none). */
export function templateVarsToText(v: unknown): string {
  const vars = valueMode(v) === 'template' ? (v as TemplateValue).vars : undefined;
  return vars && Object.keys(vars).length ? JSON.stringify(vars, null, 2) : '';
}

/** Build a Value from editor text. Invalid JSON is kept as the raw string so it is never lost. */
export function textToValue(mode: ValueMode, text: string, varsText = ''): unknown {
  switch (mode) {
    case 'reference':
      return { $from: text };
    case 'template': {
      const out: TemplateValue = { $template: text };
      if (varsText.trim()) {
        try {
          const vars = JSON.parse(varsText);
          if (vars && typeof vars === 'object' && !Array.isArray(vars)) out.vars = vars;
        } catch {
          /* leave vars unset until the JSON parses */
        }
      }
      return out;
    }
    case 'json':
      try {
        return JSON.parse(text);
      } catch {
        return text;
      }
    default:
      return text;
  }
}

/** True when a JSON-mode / template-vars editor text is not parseable. */
export function isInvalidValueJson(text: string): boolean {
  if (!text.trim()) return false;
  try {
    JSON.parse(text);
    return false;
  } catch {
    return true;
  }
}

/**
 * Insert a picked reference into a Value, in the field's current mode:
 *  - reference: replaced by the pick;
 *  - template: `{name}` is appended to the text and `name` bound to the reference in `vars`;
 *  - literal: an empty field becomes the reference; text becomes a template ending in the placeholder;
 *  - json: `{"$from": "ref"}` is inserted at `caret` (or appended).
 * Returns the new Value and the mode the editor should now show.
 */
export function insertReferenceIntoValue(
  value: unknown,
  mode: ValueMode,
  ref: string,
  name: string,
  caret?: number
): { value: unknown; mode: ValueMode } {
  if (mode === 'reference') return { value: { $from: ref }, mode };
  if (mode === 'template') {
    const t = value as TemplateValue;
    const vars = { ...(t.vars ?? {}) };
    let key = name;
    for (let i = 2; key in vars && JSON.stringify(vars[key]) !== JSON.stringify({ $from: ref }); i++) key = `${name}_${i}`;
    vars[key] = { $from: ref };
    return { value: { $template: `${t.$template ?? ''}{${key}}`, vars }, mode };
  }
  if (mode === 'json') {
    const text = valueToText(value);
    const snippet = JSON.stringify({ $from: ref });
    const at = caret === undefined ? text.length : Math.min(Math.max(caret, 0), text.length);
    return { value: textToValue('json', `${text.slice(0, at)}${snippet}${text.slice(at)}`), mode };
  }
  const text = valueToText(value);
  if (!text.trim()) return { value: { $from: ref }, mode: 'reference' };
  return { value: { $template: `${text}{${name}}`, vars: { [name]: { $from: ref } } }, mode: 'template' };
}
