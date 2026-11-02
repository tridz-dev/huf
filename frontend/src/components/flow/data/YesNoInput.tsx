import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import type { DataInputProps } from './DataInput';

const NOT_SET = 'unset';

/** A value that is only ever Yes or No: a choice, not a box to type in. Stored as true / false; "Not set" leaves it out. */
export function YesNoInput({ value, onChange, hint, testId, id, label, optional, disabled }: DataInputProps) {
  const { canManage } = useFlowPermissions();
  const current = value === true || value === 'true' ? 'yes' : value === false || value === 'false' ? 'no' : NOT_SET;
  return (
    <div className="space-y-1" data-testid={testId ? `${testId}-box` : undefined}>
      {label ? <Label htmlFor={id} size="sm" className="block min-w-0 truncate">{label}{optional ? ' (optional)' : ''}</Label> : null}
      <Select value={current} onValueChange={(v) => onChange(v === 'yes' ? true : v === 'no' ? false : undefined)} disabled={!canManage || disabled}>
        <SelectTrigger id={id} data-testid={testId} aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NOT_SET} data-testid={testId ? `${testId}-unset` : undefined}>Not set</SelectItem>
          <SelectItem value="yes" data-testid={testId ? `${testId}-yes` : undefined}>Yes</SelectItem>
          <SelectItem value="no" data-testid={testId ? `${testId}-no` : undefined}>No</SelectItem>
        </SelectContent>
      </Select>
      {hint ? <p className="text-meta leading-snug text-muted-foreground break-words">{hint}</p> : null}
    </div>
  );
}
