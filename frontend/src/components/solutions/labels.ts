/**
 * The single place for the user-facing word for a Solution. Change SOLUTION_WORD
 * (and plural) here and every Solutions screen follows.
 */
export const SOLUTION_WORD = 'Solution';
export const SOLUTIONS_WORD = 'Solutions';

export const labels = {
  solution: SOLUTION_WORD,
  solutions: SOLUTIONS_WORD,
  solutionLower: SOLUTION_WORD.toLowerCase(),
  solutionsLower: SOLUTIONS_WORD.toLowerCase(),
  purpose: 'Purpose',
  runsOn: 'Runs on',
  anyPurpose: 'Any purpose',
  newSolution: `New ${SOLUTION_WORD.toLowerCase()}`,
  activeSolutions: `Active ${SOLUTIONS_WORD.toLowerCase()}`,
} as const;

export const PURPOSE_LABELS: Record<string, string> = {
  answer: 'Answer questions',
  orders: 'Take orders',
  support: 'Support & handoff',
  bookings: 'Bookings',
  updates: 'Send updates',
  team: 'Team & internal',
  custom: 'Custom',
};

export function purposeLabel(id: string | null | undefined): string {
  if (!id) return PURPOSE_LABELS.custom;
  return PURPOSE_LABELS[id] ?? PURPOSE_LABELS.custom;
}
