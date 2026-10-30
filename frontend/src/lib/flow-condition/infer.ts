import { isNumberText } from './compile';
import { operatorInfo } from './operators';
import type { Operand, OperatorId, Rule, ScalarOperand } from './types';

/** Typed text that is only a number ("100", "-2", "2.5"; not "007", "1e3" or "1,000"). */
export const looksNumeric = (text: string): boolean => isNumberText(text.trim());

/** The words of a value, for the box it was typed in. */
export function valueText(value: Operand | undefined): string {
  if (!value || value.kind === 'ref') return '';
  if (value.kind === 'list') return value.items.map((i) => i.text).join(', ');
  return value.text;
}

const scalar = (text: string): ScalarOperand => (looksNumeric(text) ? { kind: 'number', text: text.trim() } : { kind: 'text', text });

/**
 * What typed text means for an operator: a number when it looks like one (and the operator compares numbers), else text.
 * `numeric` says to compare as numbers, so a field holding the text "150" still counts as 150.
 */
export function operandFromText(op: OperatorId, typed: string): { value?: Operand; numeric: boolean } {
  const info = operatorInfo(op);
  if (info.value === 'none') return { numeric: false };
  if (info.value === 'many') {
    const items = typed.split(',').map((p) => p.trim()).filter(Boolean).map(scalar);
    return { value: { kind: 'list', items }, numeric: items.length > 0 && items.every((i) => i.kind === 'number') };
  }
  const text = typed.trim();
  if (info.numeric && looksNumeric(text)) return { value: { kind: 'number', text }, numeric: true };
  return { value: { kind: 'text', text }, numeric: false };
}

/** The same rule with a different operator: the value is read again for the new operator (a list for "is one of"). */
export function withOperator(rule: Rule, op: OperatorId): Rule {
  const info = operatorInfo(op);
  const next: Rule = { ...rule, op };
  if (info.value === 'none') return next;
  const keepRef = rule.value?.kind === 'ref' && info.value === 'one';
  if (keepRef) return { ...next, numeric: info.numeric && rule.numeric };
  const typed = rule.raw ?? valueText(rule.value);
  const { value, numeric } = operandFromText(op, typed);
  return { ...next, value, numeric, raw: typed };
}

/** The same rule with new typed text as its value. */
export function withTypedValue(rule: Rule, typed: string): Rule {
  const { value, numeric } = operandFromText(rule.op, typed);
  return { ...rule, value, numeric, raw: typed };
}

/** The same rule comparing with another field instead of typed text. */
export function withFieldValue(rule: Rule, ref: string): Rule {
  const info = operatorInfo(rule.op);
  return { ...rule, value: { kind: 'ref', ref }, numeric: info.numeric && ['gt', 'lt', 'gte', 'lte'].includes(rule.op), raw: undefined };
}
