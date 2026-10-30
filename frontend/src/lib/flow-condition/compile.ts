/**
 * Rules -> condition expression text. Must give exactly the text `huf/ai/flow/support/condition_compile.py` gives;
 * `condition_vectors.json` pins both. See that file's docstring for the shapes.
 */
import { isOperator, needsValue } from './operators';
import type { ConditionModel, Group, Operand, OperatorId, Rule, ScalarOperand } from './types';

const COMPARE: Partial<Record<OperatorId, string>> = { is: '==', is_not: '!=', gt: '>', lt: '<', gte: '>=', lte: '<=' };
const NUMERIC_OPS = new Set<OperatorId>(['is', 'is_not', 'gt', 'lt', 'gte', 'lte', 'one_of', 'none_of']);
const TEXT_OPS = new Set<OperatorId>(['is', 'is_not', 'contains', 'not_contains', 'starts_with', 'ends_with', 'one_of', 'none_of']);
export const EMPTY_LIST = "[None, '', [], {}]";

/** FIELD_CONTRACT reference grammar: a root, then `.name` or `[n]`. */
export const REF_RE = /^(input|trigger|row|foreach\.(?:item|index)|[A-Za-z_][A-Za-z0-9_]*)((?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)$/;
const SEGMENT_RE = /\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]/g;
export const NUMBER_RE = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/;

export const isValidRef = (ref: unknown): ref is string => typeof ref === 'string' && REF_RE.test(ref);
export const isNumberText = (text: unknown): text is string => typeof text === 'string' && NUMBER_RE.test(text);

/** A single-quoted literal that reads back as exactly `value`. */
export function pyString(value: string): string {
  let out = "'";
  for (const ch of value) {
    const code = ch.codePointAt(0) as number;
    if (ch === '\\') out += '\\\\';
    else if (ch === "'") out += "\\'";
    else if (ch === '\n') out += '\\n';
    else if (ch === '\r') out += '\\r';
    else if (ch === '\t') out += '\\t';
    else if (code < 0x20 || (code >= 0x7f && code <= 0x9f)) out += `\\x${code.toString(16).padStart(2, '0')}`;
    else if (code === 0x2028 || code === 0x2029 || (code >= 0xd800 && code <= 0xdfff)) out += `\\u${code.toString(16).padStart(4, '0')}`;
    else out += ch;
  }
  return `${out}'`;
}

/** `input.customer.name` -> `input['customer']['name']`; null when it is not a reference. */
export function referenceExpression(ref: unknown): string | null {
  if (typeof ref !== 'string') return null;
  const m = REF_RE.exec(ref);
  if (!m) return null;
  const root = m[1];
  let out = root.startsWith('foreach.') ? `foreach['${root.slice(8)}']` : root;
  for (const seg of m[2].matchAll(SEGMENT_RE)) out += seg[1] !== undefined ? `['${seg[1]}']` : `[${seg[2]}]`;
  return out;
}

const isScalar = (v: unknown): v is ScalarOperand =>
  !!v && typeof v === 'object' && ((v as ScalarOperand).kind === 'text' || (v as ScalarOperand).kind === 'number') && typeof (v as ScalarOperand).text === 'string';

function completeValue(op: OperatorId, value: Operand | undefined): boolean {
  if (!needsValue(op)) return true;
  if (!value || typeof value !== 'object') return false;
  switch (value.kind) {
    case 'text':
      return typeof value.text === 'string' && value.text !== '';
    case 'number':
      return isNumberText(value.text);
    case 'ref':
      return isValidRef(value.ref);
    case 'list':
      return (op === 'one_of' || op === 'none_of') && Array.isArray(value.items) && value.items.length > 0 && value.items.every((i) => isScalar(i) && completeValue(op, i));
    default:
      return false;
  }
}

/** Whether a rule says something the flow can use (a field, and a value where the operator needs one). */
export function isCompleteRule(rule: Rule): boolean {
  if (!rule || typeof rule !== 'object' || !isOperator(rule.op)) return false;
  if (referenceExpression(rule.field) === null) return false;
  if (!completeValue(rule.op, rule.value)) return false;
  const list = rule.value?.kind === 'list';
  if (needsValue(rule.op)) return rule.op === 'one_of' || rule.op === 'none_of' ? list : !list;
  return true;
}

/** The flags that actually apply to a rule (compare as numbers / ignore capital letters), after the rules of what makes sense. */
export function effectiveFlags(rule: Rule): { numeric: boolean; ignoreCase: boolean } {
  const v = rule.value;
  let numeric = false;
  let hasText = false;
  if (v?.kind === 'list') {
    numeric = !!rule.numeric && v.items.every((i) => i.kind === 'number');
    hasText = v.items.some((i) => i.kind === 'text');
  } else if (v) {
    numeric = !!rule.numeric && (v.kind === 'number' || v.kind === 'ref') && NUMERIC_OPS.has(rule.op);
    hasText = v.kind === 'text' || v.kind === 'ref';
  }
  const ignoreCase = !!rule.ignoreCase && !numeric && hasText && TEXT_OPS.has(rule.op);
  return { numeric, ignoreCase };
}

/** The text of one rule, or null when it is not complete. */
export function compileRule(rule: Rule): string | null {
  if (!isCompleteRule(rule)) return null;
  const field = referenceExpression(rule.field) as string;
  switch (rule.op) {
    case 'is_empty':
      return `${field} in ${EMPTY_LIST}`;
    case 'is_not_empty':
      return `${field} not in ${EMPTY_LIST}`;
    case 'is_yes':
      return `${field} == True`;
    case 'is_no':
      return `${field} == False`;
    default:
  }
  const value = rule.value as Operand;
  const { numeric, ignoreCase } = effectiveFlags(rule);
  const fieldSide = numeric ? `number(${field})` : ignoreCase ? `lower(${field})` : field;
  const scalar = (v: Operand): string => {
    if (v.kind === 'text') return ignoreCase ? `lower(${pyString(v.text)})` : pyString(v.text);
    if (v.kind === 'number') return v.text;
    if (v.kind === 'ref') {
      const r = referenceExpression(v.ref) as string;
      return numeric ? `number(${r})` : ignoreCase ? `lower(${r})` : r;
    }
    return '';
  };
  const symbol = COMPARE[rule.op];
  if (symbol) return `${fieldSide} ${symbol} ${scalar(value)}`;
  switch (rule.op) {
    case 'contains':
      return `${scalar(value)} in ${fieldSide}`;
    case 'not_contains':
      return `not (${scalar(value)} in ${fieldSide})`;
    case 'starts_with':
      return `startswith(${fieldSide}, ${scalar(value)})`;
    case 'ends_with':
      return `endswith(${fieldSide}, ${scalar(value)})`;
    default: {
      const items = value.kind === 'list' ? value.items : [];
      return `${fieldSide} ${rule.op === 'one_of' ? 'in' : 'not in'} [${items.map(scalar).join(', ')}]`;
    }
  }
}

function compileItems(items: Array<Rule | Group>, allowGroups: boolean): string[] {
  const parts: string[] = [];
  for (const item of items ?? []) {
    if (!item || typeof item !== 'object') continue;
    if (item.type === 'group') {
      if (!allowGroups) continue;
      const inner = compileItems(item.items, false);
      if (inner.length) parts.push(`(${inner.join(item.match === 'any' ? ' or ' : ' and ')})`);
    } else {
      const text = compileRule(item);
      if (text !== null) parts.push(text);
    }
  }
  return parts;
}

/** The expression for a rules model; '' when there is no complete rule. */
export function compileCondition(model: ConditionModel): string {
  if (!model || typeof model !== 'object') return '';
  return compileItems(model.items, true).join(model.match === 'any' ? ' or ' : ' and ');
}

/** The model as `parseCondition(compileCondition(model))` gives it back: complete rules only, flags that apply, no screen-only fields. */
export function canonicalModel(model: ConditionModel): ConditionModel {
  const rule = (r: Rule): Rule => {
    const { numeric, ignoreCase } = effectiveFlags(r);
    const out: Rule = { type: 'rule', field: r.field, op: r.op };
    if (needsValue(r.op) && r.value) {
      out.value =
        r.value.kind === 'list' ? { kind: 'list', items: r.value.items.map((i) => ({ ...i })) } : r.value.kind === 'text' ? { kind: 'text', text: r.value.text } : r.value.kind === 'number' ? { kind: 'number', text: r.value.text } : { kind: 'ref', ref: r.value.ref };
    }
    if (numeric) out.numeric = true;
    if (ignoreCase) out.ignoreCase = true;
    return out;
  };
  const items: Array<Rule | Group> = [];
  for (const item of model.items ?? []) {
    if (item.type === 'group') {
      const inner = item.items.filter(isCompleteRule).map(rule);
      if (inner.length) items.push({ type: 'group', match: inner.length > 1 ? item.match : 'all', items: inner });
    } else if (isCompleteRule(item)) items.push(rule(item));
  }
  return { match: items.length > 1 ? model.match : 'all', items };
}
