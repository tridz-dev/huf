/**
 * The rules a Condition step is built from (UX-13). The step stores one expression string; this model is what the
 * builder edits and what `compile.ts` turns into that string and `parse.ts` reads back from it.
 * Mirrors `huf/ai/flow/support/condition_compile.py` (the docstring there is the full description of the model).
 */

export type Match = 'all' | 'any';

export type OperatorId =
  | 'is'
  | 'is_not'
  | 'gt'
  | 'lt'
  | 'gte'
  | 'lte'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'is_empty'
  | 'is_not_empty'
  | 'is_yes'
  | 'is_no'
  | 'one_of'
  | 'none_of';

export type ScalarOperand = { kind: 'text'; text: string } | { kind: 'number'; text: string };
export type Operand = ScalarOperand | { kind: 'ref'; ref: string } | { kind: 'list'; items: ScalarOperand[] };

export interface Rule {
  type: 'rule';
  /** Screen only: keeps a row's identity while editing. Never compiled. */
  id?: string;
  /** Reference path of the data checked (`input.amount`, `n1.customer.name`). '' = not chosen yet. */
  field: string;
  op: OperatorId;
  value?: Operand;
  /** Compare as numbers (so the text "150" from a form counts as 150). */
  numeric?: boolean;
  /** Text matching that ignores capital letters. */
  ignoreCase?: boolean;
  /** Screen only: what was typed in the value box, so a trailing comma or space is not lost while typing. */
  raw?: string;
}

export interface Group {
  type: 'group';
  id?: string;
  match: Match;
  items: Rule[];
}

export interface ConditionModel {
  match: Match;
  items: Array<Rule | Group>;
}

export const MAX_EXPRESSION_LENGTH = 500;
