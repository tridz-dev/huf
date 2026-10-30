import { isCompleteRule } from './compile';
import { operatorInfo } from './operators';
import type { ConditionModel, Operand, Rule } from './types';

/** "Amount is more than 100 and Status is Paid" for the complete rules; null when there is none. `labelOf` names a field in words. */
export function describeCondition(model: ConditionModel, labelOf: (ref: string) => string): string | null {
  const value = (v: Operand | undefined): string => {
    if (!v) return '';
    if (v.kind === 'ref') return labelOf(v.ref);
    if (v.kind === 'list') {
      const parts = v.items.map((i) => i.text);
      return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} or ${parts[parts.length - 1]}` : parts[0] ?? '';
    }
    return v.text;
  };
  const rule = (r: Rule) => `${labelOf(r.field)} ${operatorInfo(r.op).phrase}${operatorInfo(r.op).value === 'none' ? '' : ` ${value(r.value)}`}`;
  const parts: string[] = [];
  for (const item of model.items) {
    if (item.type === 'group') {
      const inner = item.items.filter(isCompleteRule).map(rule);
      if (inner.length > 1) parts.push(`(${inner.join(item.match === 'any' ? ' or ' : ' and ')})`);
      else if (inner.length) parts.push(inner[0]);
    } else if (isCompleteRule(item)) parts.push(rule(item));
  }
  return parts.length ? parts.join(model.match === 'any' ? ' or ' : ' and ') : null;
}
