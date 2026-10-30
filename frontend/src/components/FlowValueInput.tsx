import { DataInput, type DataKind } from './flow/data/DataInput';

interface FlowValueInputProps {
  id: string;
  label: string;
  value: unknown;
  onChange: (value: unknown) => void;
  optional?: boolean;
  /** data-testid of the box; the "+ Use data" button is `${testId}-picker`. */
  testId?: string;
  /** Step this field belongs to: "Use data" lists the trigger and the steps before it. */
  nodeId?: string;
  /** Example shown in an empty box. */
  placeholder?: string;
  /** One line under the box: where to find the value. */
  hint?: string;
  kind?: DataKind;
  /** `list`: the field takes a whole list. */
  accept?: 'value' | 'list';
}

/**
 * A labelled value box for a step. It is `DataInput` (see components/flow/data): typed text and data chips in one box,
 * no "how the value is given" choice. Kept under this name so the step forms keep working while they move to `DataInput`.
 */
export function FlowValueInput({ id, label, value, onChange, optional, testId, nodeId, placeholder, hint, kind, accept }: FlowValueInputProps) {
  return (
    <DataInput id={id} label={label} value={value} onChange={onChange} optional={optional} testId={testId} nodeId={nodeId} placeholder={placeholder} hint={hint} kind={kind} accept={accept} />
  );
}
