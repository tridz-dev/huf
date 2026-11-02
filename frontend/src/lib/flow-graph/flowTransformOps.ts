/**
 * Transform ops understood by the backend (huf/ai/graph/transforms.py REGISTRY and
 * graph_ir.schema.json $defs/TransformOp). flowTransformOps.test.ts keeps this list in
 * lockstep with the backend; add a new op in both places.
 */
export interface TransformOpSpec {
  name: string;
  /** Plain name shown in the picker and on the step card. */
  label: string;
  group: 'text' | 'rows';
  /** Labelled group in the picker. */
  section: TransformSection;
  /** `input` keys. Keys in `optional` may be left blank. */
  params: string[];
  optional?: string[];
}

export type TransformSection = 'change-text' | 'find-in-text' | 'pick-rows' | 'group-combine' | 'values';

/** Picker groups in display order. */
export const TRANSFORM_SECTIONS: Array<{ id: TransformSection; title: string }> = [
  { id: 'change-text', title: 'Change text' },
  { id: 'find-in-text', title: 'Check or find in text' },
  { id: 'pick-rows', title: 'Pick and sort rows' },
  { id: 'group-combine', title: 'Group and combine rows' },
  { id: 'values', title: 'Fill in blanks' },
];

export const TRANSFORM_OPS: TransformOpSpec[] = [
  { name: 'lower', label: 'Make lowercase', group: 'text', section: 'change-text', params: ['text'] },
  { name: 'upper', label: 'Make uppercase', group: 'text', section: 'change-text', params: ['text'] },
  { name: 'trim', label: 'Remove extra spaces', group: 'text', section: 'change-text', params: ['text'] },
  { name: 'replace', label: 'Replace text', group: 'text', section: 'change-text', params: ['text', 'find', 'with', 'count'], optional: ['with', 'count'] },
  { name: 'split_first', label: 'Take the first part', group: 'text', section: 'change-text', params: ['text', 'separator'], optional: ['separator'] },
  { name: 'concat', label: 'Join text together', group: 'text', section: 'change-text', params: ['parts', 'separator'], optional: ['separator'] },
  { name: 'contains', label: 'Contains the words', group: 'text', section: 'find-in-text', params: ['text', 'needle', 'ignore_case'], optional: ['ignore_case'] },
  { name: 'starts_with', label: 'Starts with the words', group: 'text', section: 'find-in-text', params: ['text', 'prefix', 'ignore_case'], optional: ['ignore_case'] },
  { name: 'regex_extract', label: 'Find with a pattern', group: 'text', section: 'find-in-text', params: ['text', 'pattern', 'group', 'default'], optional: ['group', 'default'] },
  { name: 'select', label: 'Keep only some fields', group: 'rows', section: 'pick-rows', params: ['rows', 'fields'] },
  { name: 'filter', label: 'Keep rows that match', group: 'rows', section: 'pick-rows', params: ['rows', 'where'] },
  { name: 'sort', label: 'Sort rows', group: 'rows', section: 'pick-rows', params: ['rows', 'key', 'order'], optional: ['order'] },
  { name: 'limit', label: 'Keep the first rows', group: 'rows', section: 'pick-rows', params: ['rows', 'count'] },
  { name: 'distinct', label: 'Remove duplicates', group: 'rows', section: 'pick-rows', params: ['rows', 'key'], optional: ['key'] },
  { name: 'group_by', label: 'Group rows', group: 'rows', section: 'group-combine', params: ['rows', 'key'] },
  { name: 'aggregate', label: 'Count or add up', group: 'rows', section: 'group-combine', params: ['rows', 'op', 'field'], optional: ['field'] },
  { name: 'batch', label: 'Split into groups', group: 'rows', section: 'group-combine', params: ['rows', 'size'] },
  { name: 'join', label: 'Combine two lists', group: 'rows', section: 'group-combine', params: ['left', 'right', 'left_key', 'right_key', 'how'], optional: ['how'] },
  { name: 'lookup', label: 'Add matching details', group: 'rows', section: 'group-combine', params: ['rows', 'from', 'key', 'on', 'as'], optional: ['on'] },
  { name: 'coalesce', label: 'First value that is not empty', group: 'rows', section: 'values', params: ['values'] },
];

export const TRANSFORM_OP_NAMES: string[] = TRANSFORM_OPS.map((o) => o.name);

export function getTransformOp(name: string | undefined): TransformOpSpec | undefined {
  return TRANSFORM_OPS.find((o) => o.name === name);
}
