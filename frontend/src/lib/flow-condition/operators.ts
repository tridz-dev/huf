import type { OperatorId, Rule } from './types';

export interface OperatorInfo {
  id: OperatorId;
  /** In the list: "is more than". */
  label: string;
  /** In the sentence: "Amount is more than 100". */
  phrase: string;
  value: 'none' | 'one' | 'many';
  /** Compares text, so "ignore capital letters" can apply. */
  text: boolean;
  /** Compares numbers, so a number value is compared as a number. */
  numeric: boolean;
}

export const OPERATORS: OperatorInfo[] = [
  { id: 'is', label: 'is', phrase: 'is', value: 'one', text: true, numeric: true },
  { id: 'is_not', label: 'is not', phrase: 'is not', value: 'one', text: true, numeric: true },
  { id: 'gt', label: 'is more than', phrase: 'is more than', value: 'one', text: false, numeric: true },
  { id: 'lt', label: 'is less than', phrase: 'is less than', value: 'one', text: false, numeric: true },
  { id: 'gte', label: 'is at least', phrase: 'is at least', value: 'one', text: false, numeric: true },
  { id: 'lte', label: 'is at most', phrase: 'is at most', value: 'one', text: false, numeric: true },
  { id: 'contains', label: 'contains', phrase: 'contains', value: 'one', text: true, numeric: false },
  { id: 'not_contains', label: 'does not contain', phrase: 'does not contain', value: 'one', text: true, numeric: false },
  { id: 'starts_with', label: 'starts with', phrase: 'starts with', value: 'one', text: true, numeric: false },
  { id: 'ends_with', label: 'ends with', phrase: 'ends with', value: 'one', text: true, numeric: false },
  { id: 'one_of', label: 'is one of', phrase: 'is one of', value: 'many', text: true, numeric: true },
  { id: 'none_of', label: 'is none of', phrase: 'is none of', value: 'many', text: true, numeric: true },
  { id: 'is_empty', label: 'is empty', phrase: 'is empty', value: 'none', text: false, numeric: false },
  { id: 'is_not_empty', label: 'is not empty', phrase: 'is not empty', value: 'none', text: false, numeric: false },
  { id: 'is_yes', label: 'is yes', phrase: 'is yes', value: 'none', text: false, numeric: false },
  { id: 'is_no', label: 'is no', phrase: 'is no', value: 'none', text: false, numeric: false },
];

const BY_ID = new Map(OPERATORS.map((o) => [o.id, o]));
export const operatorInfo = (id: OperatorId): OperatorInfo => BY_ID.get(id) as OperatorInfo;
export const isOperator = (v: unknown): v is OperatorId => typeof v === 'string' && BY_ID.has(v as OperatorId);

export const needsValue = (op: OperatorId): boolean => operatorInfo(op).value !== 'none';

/** What the value box says before anything is typed. */
export function valuePlaceholder(op: OperatorId): string {
  switch (op) {
    case 'gt':
    case 'lt':
    case 'gte':
    case 'lte':
      return 'A number, e.g. 100';
    case 'one_of':
    case 'none_of':
      return 'Values separated by commas';
    default:
      return 'A value';
  }
}

export const newRuleId = (() => {
  let n = 0;
  return () => `rule-${Date.now().toString(36)}-${++n}`;
})();

export const emptyRule = (): Rule => ({ type: 'rule', id: newRuleId(), field: '', op: 'is', ignoreCase: true });
