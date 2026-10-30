import { useMemo } from 'react';
import { describeChip, type PickerModel } from '@/lib/flow-data/model';
import { describeCondition } from '@/lib/flow-condition/sentence';
import { parseCondition } from '@/lib/flow-condition/parse';

/** How a field reads on a chip: "Amount . New order". */
export function chipText(ref: string, model: PickerModel): { text: string; sample: string; missing: boolean } {
  const info = describeChip({ id: 'c', name: 'c', ref }, model);
  return { text: info.missing ? `Missing: ${info.stepTitle}` : info.stepTitle ? `${info.label} · ${info.stepTitle}` : info.label, sample: info.sample, missing: info.missing };
}

/** A field in a sentence: "Customer > Name . New order" reads "Customer name" (no step, no arrows). */
export function fieldWords(ref: string, model: PickerModel): string {
  const info = describeChip({ id: 'c', name: 'c', ref }, model);
  return info.label.replace(/ > /g, ' ').replace(/ ([A-Z])([a-z])/g, (_m, a: string, b: string) => ` ${a.toLowerCase()}${b}`);
}

/** The sentence under the builder, without "Yes when": null when no rule is complete. */
export function useConditionSentence(expression: string, model: PickerModel): string | null {
  return useMemo(() => {
    const parsed = parseCondition(expression);
    return parsed ? describeCondition(parsed, (ref) => fieldWords(ref, model)) : null;
  }, [expression, model]);
}

