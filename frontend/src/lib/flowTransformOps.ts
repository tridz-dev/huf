/**
 * Transform ops understood by the backend (huf/ai/graph/transforms.py REGISTRY and
 * graph_ir.schema.json $defs/TransformOp). flowTransformOps.test.ts keeps this list in
 * lockstep with the backend; add a new op in both places.
 */
export interface TransformOpSpec {
  name: string;
  label: string;
  group: 'text' | 'rows';
  /** `input` keys. Keys in `optional` may be left blank. */
  params: string[];
  optional?: string[];
}

export const TRANSFORM_OPS: TransformOpSpec[] = [
  { name: 'lower', label: 'Lowercase', group: 'text', params: ['text'] },
  { name: 'upper', label: 'Uppercase', group: 'text', params: ['text'] },
  { name: 'trim', label: 'Trim whitespace', group: 'text', params: ['text'] },
  { name: 'replace', label: 'Replace text', group: 'text', params: ['text', 'find', 'with', 'count'], optional: ['count'] },
  { name: 'contains', label: 'Contains', group: 'text', params: ['text', 'needle', 'ignore_case'], optional: ['ignore_case'] },
  { name: 'starts_with', label: 'Starts with', group: 'text', params: ['text', 'prefix', 'ignore_case'], optional: ['ignore_case'] },
  { name: 'split_first', label: 'Split (first part)', group: 'text', params: ['text', 'separator'], optional: ['separator'] },
  { name: 'regex_extract', label: 'Regex extract', group: 'text', params: ['text', 'pattern', 'group', 'default'], optional: ['group', 'default'] },
  { name: 'concat', label: 'Concatenate', group: 'text', params: ['parts', 'separator'], optional: ['separator'] },
  { name: 'select', label: 'Select fields', group: 'rows', params: ['rows', 'fields'] },
  { name: 'filter', label: 'Filter rows', group: 'rows', params: ['rows', 'where'] },
  { name: 'sort', label: 'Sort rows', group: 'rows', params: ['rows', 'key', 'order'], optional: ['order'] },
  { name: 'limit', label: 'Limit rows', group: 'rows', params: ['rows', 'count'] },
  { name: 'group_by', label: 'Group by', group: 'rows', params: ['rows', 'key'] },
  { name: 'aggregate', label: 'Aggregate', group: 'rows', params: ['rows', 'op', 'field'], optional: ['field'] },
  { name: 'join', label: 'Join', group: 'rows', params: ['left', 'right', 'left_key', 'right_key', 'how'], optional: ['how'] },
  { name: 'lookup', label: 'Lookup', group: 'rows', params: ['rows', 'from', 'key', 'on', 'as'], optional: ['on'] },
  { name: 'batch', label: 'Batch', group: 'rows', params: ['rows', 'size'] },
  { name: 'distinct', label: 'Distinct', group: 'rows', params: ['rows', 'key'], optional: ['key'] },
  { name: 'coalesce', label: 'Coalesce', group: 'rows', params: ['values'] },
];

export const TRANSFORM_OP_NAMES: string[] = TRANSFORM_OPS.map((o) => o.name);

export function getTransformOp(name: string | undefined): TransformOpSpec | undefined {
  return TRANSFORM_OPS.find((o) => o.name === name);
}
