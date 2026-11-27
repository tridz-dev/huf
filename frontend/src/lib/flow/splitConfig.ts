/** Rules of a split step (graph-IR `split`), shared by the settings form and the flow check. Mirrors huf/ai/flow/nodes/split.py. */

export interface SplitBranch {
  label?: unknown;
  weight?: unknown;
}

export interface SplitProblem {
  field: 'options' | 'holdout' | 'salt';
  message: string;
}

/** Longest branch name shown on the canvas. */
export const SPLIT_LABEL_MAX = 60;
/** Longest bucketing salt. */
export const SPLIT_SALT_MAX = 140;

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** Sum of the branch weights that are numbers. */
export function splitWeightTotal(branches: SplitBranch[]): number {
  return branches.reduce((sum, b) => sum + (isNum(b.weight) ? b.weight : 0), 0);
}

/** Readable problems with a split's branches, holdout and salt. Empty when it can be saved. */
export function splitProblems(branches: SplitBranch[], holdout: unknown, salt: unknown): SplitProblem[] {
  const out: SplitProblem[] = [];
  const add = (field: SplitProblem['field'], message: string) => out.push({ field, message });
  if (branches.length < 2) add('options', 'Add at least two branches.');
  if (branches.some((b) => typeof b.label !== 'string' || b.label.trim() === '')) add('options', 'Give every branch a name.');
  const names = branches.map((b) => (typeof b.label === 'string' ? b.label.trim().toLowerCase() : '')).filter(Boolean);
  if (new Set(names).size !== names.length) add('options', 'Give each branch a different name.');
  if (branches.some((b) => !isNum(b.weight) || b.weight < 0 || b.weight > 100)) add('options', 'Every branch needs a share from 0 to 100.');
  else if (branches.length > 0 && Math.abs(splitWeightTotal(branches) - 100) > 1e-9) add('options', 'The branch shares must add up to 100.');
  if (holdout !== undefined && (!isNum(holdout) || holdout < 0 || holdout > 100)) add('holdout', 'The holdout must be a number from 0 to 100.');
  if (salt !== undefined && (typeof salt !== 'string' || salt.length > SPLIT_SALT_MAX)) add('salt', `Keep the salt under ${SPLIT_SALT_MAX} characters.`);
  return out;
}
