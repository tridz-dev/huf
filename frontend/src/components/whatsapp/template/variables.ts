export type VariableType = 'number' | 'name';

export const NAMED_VARIABLE_RE = /^[a-z][a-z0-9_]*$/;
const TOKEN_RE = /\{\{\s*([^{}]*?)\s*\}\}/g;

export interface VariableToken {
  /** Text between the braces, trimmed ("1", "first_name"). */
  token: string;
  kind: VariableType | 'invalid';
  start: number;
  end: number;
}

function kindOf(token: string): VariableToken['kind'] {
  if (/^[1-9]\d*$/.test(token)) return 'number';
  if (NAMED_VARIABLE_RE.test(token)) return 'name';
  return 'invalid';
}

/** Every `{{...}}` occurrence in order, including repeats and malformed ones. */
export function findVariableTokens(text: string): VariableToken[] {
  const out: VariableToken[] = [];
  for (const m of text.matchAll(TOKEN_RE)) {
    const start = m.index ?? 0;
    out.push({ token: m[1], kind: kindOf(m[1]), start, end: start + m[0].length });
  }
  return out;
}

/** Valid variable tokens, once each, in order of first appearance. */
export function extractVariables(text: string, type?: VariableType): string[] {
  const seen: string[] = [];
  for (const t of findVariableTokens(text)) {
    if (t.kind === 'invalid' || (type && t.kind !== type)) continue;
    if (!seen.includes(t.token)) seen.push(t.token);
  }
  return seen;
}

/** True when any `{{` or `}}` is left once well-formed variables are removed. */
export function hasStrayBraces(text: string): boolean {
  return /\{\{|\}\}/.test(text.replace(TOKEN_RE, ''));
}

export function nextVariableNumber(text: string): number {
  const numbers = findVariableTokens(text)
    .filter((t) => t.kind === 'number')
    .map((t) => Number(t.token));
  return numbers.length ? Math.max(...numbers) + 1 : 1;
}

export function nextVariableName(text: string): string {
  const used = new Set(extractVariables(text, 'name'));
  let n = 1;
  while (used.has(`variable_${n}`)) n += 1;
  return `variable_${n}`;
}

/** Insert the next variable at the caret (or the end when the caret is unknown). */
export function insertVariable(
  text: string,
  caret: number | null,
  kind: VariableType,
): { text: string; caret: number; token: string } {
  const at = caret === null || caret < 0 || caret > text.length ? text.length : caret;
  const token = kind === 'number' ? String(nextVariableNumber(text)) : nextVariableName(text);
  const insert = `{{${token}}}`;
  return { text: text.slice(0, at) + insert + text.slice(at), caret: at + insert.length, token };
}

function rewrite(text: string, map: Record<string, string>): string {
  return text.replace(TOKEN_RE, (match, token: string) => (token in map ? `{{${map[token]}}}` : match));
}

/** Renumber numbered variables 1..n by first appearance; `map` is old token -> new token. */
export function renumberVariables(text: string): { text: string; map: Record<string, string> } {
  const map: Record<string, string> = {};
  extractVariables(text, 'number').forEach((token, i) => {
    map[token] = String(i + 1);
  });
  return { text: rewrite(text, map), map };
}

/** Convert every variable to the other style ({{2}} <-> {{variable_2}}). */
export function convertVariableType(
  text: string,
  to: VariableType,
): { text: string; map: Record<string, string> } {
  const map: Record<string, string> = {};
  if (to === 'name') {
    for (const token of extractVariables(text, 'number')) map[token] = `variable_${token}`;
  } else {
    extractVariables(text, 'name').forEach((token, i) => {
      map[token] = String(i + 1);
    });
  }
  return { text: rewrite(text, map), map };
}

/** Move sample values to their renamed keys; `prefix` is "header." for header samples. */
export function remapSamples(
  samples: Record<string, string>,
  map: Record<string, string>,
  prefix = '',
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(samples)) {
    if (!key.startsWith(prefix)) {
      out[key] = value;
      continue;
    }
    const bare = key.slice(prefix.length);
    out[prefix + (map[bare] ?? bare)] = value;
  }
  return out;
}

/** Replace variables with their samples; blank samples keep the placeholder visible. */
export function fillDraftVariables(text: string, samples: Record<string, string>, prefix = ''): string {
  return text.replace(TOKEN_RE, (match, token: string) => {
    const value = samples[prefix + token];
    return value && value.trim() ? value : match;
  });
}
