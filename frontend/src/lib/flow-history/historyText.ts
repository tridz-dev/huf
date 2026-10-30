/** What the "Node deleted" toast says about what went (the step, and the steps that only it led to). */
export function removedDescription(label: string | undefined, removedCount: number): string | undefined {
  if (removedCount > 1) return `"${label ?? 'The step'}" and ${removedCount - 1} step${removedCount - 1 === 1 ? '' : 's'} after it were removed from the flow.`;
  return label ? `"${label}" was removed from the flow.` : undefined;
}
