import { X } from 'lucide-react';
import { Button } from '../../ui/button';
import { Checkbox } from '../../ui/checkbox';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import type { PickerModel } from '@/lib/flow-data/model';
import { isCompleteRule } from '@/lib/flow-condition/compile';
import { valueText, withFieldValue, withOperator, withTypedValue } from '@/lib/flow-condition/infer';
import { OPERATORS, operatorInfo, valuePlaceholder } from '@/lib/flow-condition/operators';
import type { OperatorId, Rule } from '@/lib/flow-condition/types';
import { cn } from '@/lib/utils';
import { DataPickPopover } from './DataPickPopover';
import { chipText } from './conditionLabels';

interface Props {
  rule: Rule;
  /** Where this row is, for test ids and names: "flow-condition-row-0" or "flow-condition-group-1-row-0". */
  testId: string;
  /** "Rule 2" for screen readers. */
  name: string;
  model: PickerModel;
  loading: boolean;
  refresh: () => void;
  disabled?: boolean;
  onChange: (next: Rule) => void;
  onRemove: () => void;
}

const chipClass = 'inline-flex min-h-control-md w-full min-w-0 items-center gap-1 rounded-md border px-2 py-1 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal';

/** One rule: the data checked, how, and against what. A rule that is not finished says what is missing. */
export function RuleRow({ rule, testId, name, model, loading, refresh, disabled, onChange, onRemove }: Props) {
  const info = operatorInfo(rule.op);
  const complete = isCompleteRule(rule);
  const field = rule.field ? chipText(rule.field, model) : null;
  const valueRef = rule.value?.kind === 'ref' ? rule.value.ref : null;
  const other = valueRef ? chipText(valueRef, model) : null;
  const showCase = info.text && rule.value?.kind !== 'number' && rule.value?.kind !== 'list' ? true : info.text && rule.value?.kind === 'list' && rule.value.items.some((i) => i.kind === 'text');
  const missing = !rule.field ? 'Choose the data to check.' : info.value !== 'none' && !complete ? 'Add the value to compare with.' : '';

  return (
    <div className="space-y-2 rounded-md border border-border p-2" data-testid={testId} role="group" aria-label={name}>
      <div className="flex items-start gap-1.5">
        <div className="min-w-0 flex-1">
          <DataPickPopover model={model} loading={loading} refresh={refresh} disabled={disabled} onPick={(p) => onChange({ ...rule, field: p.ref })}>
            <button
              type="button"
              disabled={disabled}
              className={cn(chipClass, field ? (field.missing ? 'border-destructive bg-destructive-tint text-destructive' : 'border-border bg-muted text-foreground hover:border-signal') : 'border-dashed border-border text-muted-foreground hover:border-signal')}
              aria-label={field ? `Data checked in ${name}: ${field.text}. Press Enter to change.` : `Choose the data to check in ${name}`}
              title={field?.sample ? `${field.sample} (example)` : undefined}
              data-testid={`${testId}-field`}
            >
              <span className="min-w-0 truncate">{field ? field.text : 'Choose data to check'}</span>
              {field?.sample ? <span className="ml-auto shrink-0 truncate text-muted-foreground">e.g. {field.sample}</span> : null}
            </button>
          </DataPickPopover>
        </div>
        {!disabled && (
          <Button type="button" variant="ghost" size="icon" className="h-control-md w-control-md shrink-0" aria-label={`Remove ${name}`} data-testid={`${testId}-remove`} onClick={onRemove}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <Select value={rule.op} disabled={disabled} onValueChange={(v) => onChange(withOperator(rule, v as OperatorId))}>
        <SelectTrigger aria-label={`How ${name} compares`} data-testid={`${testId}-op`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {OPERATORS.map((o) => (
            <SelectItem key={o.id} value={o.id} data-testid={`flow-option-condition-op-${o.id}`}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {info.value !== 'none' && (
        <div className="space-y-1.5">
          {other ? (
            <div className="flex items-start gap-1.5">
              <DataPickPopover model={model} loading={loading} refresh={refresh} disabled={disabled} onPick={(p) => onChange(withFieldValue(rule, p.ref))}>
                <button
                  type="button"
                  disabled={disabled}
                  className={cn(chipClass, other.missing ? 'border-destructive bg-destructive-tint text-destructive' : 'border-border bg-muted hover:border-signal')}
                  aria-label={`Compared with ${other.text}. Press Enter to change.`}
                  data-testid={`${testId}-value`}
                >
                  <span className="min-w-0 truncate">{other.text}</span>
                </button>
              </DataPickPopover>
              {!disabled && (
                <Button type="button" variant="ghost" size="icon" className="h-control-md w-control-md shrink-0" aria-label="Type a value instead" title="Type a value instead" data-testid={`${testId}-value-clear`} onClick={() => onChange(withTypedValue({ ...rule, raw: undefined }, ''))}>
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          ) : (
            <div className="flex items-start gap-1.5">
              <Input
                aria-label={`Value for ${name}`}
                disabled={disabled}
                value={rule.raw ?? valueText(rule.value)}
                placeholder={valuePlaceholder(rule.op)}
                inputMode={rule.op === 'gt' || rule.op === 'lt' || rule.op === 'gte' || rule.op === 'lte' ? 'decimal' : 'text'}
                data-testid={`${testId}-value`}
                onChange={(e) => onChange(withTypedValue(rule, e.target.value))}
                className="min-w-0 flex-1"
              />
              {info.value === 'one' && !disabled && (
                <DataPickPopover model={model} loading={loading} refresh={refresh} onPick={(p) => onChange(withFieldValue(rule, p.ref))}>
                  <Button type="button" variant="ghost" size="sm" className="shrink-0 text-signal-ink" data-testid={`${testId}-value-picker`} aria-label={`Compare ${name} with other data`}>
                    + Use data
                  </Button>
                </DataPickPopover>
              )}
            </div>
          )}
          {showCase && (
            <div className="flex items-center gap-2">
              <Checkbox
                id={`${testId}-case`}
                checked={!!rule.ignoreCase}
                disabled={disabled}
                data-testid={`${testId}-ignore-case`}
                onCheckedChange={(v) => onChange({ ...rule, ignoreCase: v === true })}
              />
              <Label htmlFor={`${testId}-case`} size="sm" className="font-normal">
                Ignore capital letters
              </Label>
            </div>
          )}
        </div>
      )}

      {missing && !disabled ? (
        <p className="text-meta text-muted-foreground" data-testid={`${testId}-unfinished`}>
          {missing}
        </p>
      ) : null}
    </div>
  );
}
