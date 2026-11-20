/**
 * FilterBuilder / FilterEditor (DESIGN.md §6.11.5): build filter conditions
 * as sentences. Field → operator (only the ones that fit the column type) →
 * a value editor for that type. Applied conditions show as FilterChips; each
 * chip reopens the same editor. Values travel as text ("Yes"/"No" for
 * checkboxes) so callers map them to their own query language once.
 */
import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { FilterChip } from './FilterChip';
import { formatCell, isNumeric, type ColumnType, type GridColumn } from './types';

export type FilterOp =
  | 'is' | 'is not' | 'contains' | 'does not contain'
  | 'is more than' | 'is less than' | 'is at least' | 'is at most'
  | 'is before' | 'is after' | 'is empty' | 'is not empty';

export interface FilterCondition {
  field: string;
  op: FilterOp;
  /** Text form of the value; '' for is empty / is not empty; "Yes"/"No" for checkbox. */
  value: string;
}

const EMPTY: FilterOp[] = ['is empty', 'is not empty'];
const TEXT: FilterOp[] = ['is', 'is not', 'contains', 'does not contain', ...EMPTY];
const NUM: FilterOp[] = ['is', 'is not', 'is more than', 'is less than', 'is at least', 'is at most', ...EMPTY];
const DATE: FilterOp[] = ['is', 'is not', 'is before', 'is after', ...EMPTY];

/** Plain-word operators that make sense for a column type. */
export function filterOpsFor(type: ColumnType): FilterOp[] {
  if (isNumeric(type)) return NUM;
  if (type === 'date') return DATE;
  if (type === 'checkbox') return ['is'];
  if (type === 'select' || type === 'link') return ['is', 'is not', ...EMPTY];
  return TEXT;
}

export const filterNeedsValue = (op: FilterOp) => !EMPTY.includes(op);

/** Chip value text for a condition, formatted for the column type. */
export function filterValueText(cond: FilterCondition, col?: Pick<GridColumn, 'type' | 'options' | 'currency'>): string | undefined {
  if (!filterNeedsValue(cond.op)) return undefined;
  if (!col || col.type === 'checkbox') return cond.value;
  const typed = isNumeric(col.type) && cond.value.trim() !== '' && Number.isFinite(Number(cond.value)) ? Number(cond.value) : cond.value;
  return formatCell(col, typed) || cond.value;
}

export interface FilterValueInputProps {
  col: Pick<GridColumn, 'type' | 'options' | 'label'>;
  value: string;
  onChange: (value: string) => void;
  id?: string;
}

/** One value editor per column type. */
export function FilterValueInput({ col, value, onChange, id }: FilterValueInputProps) {
  if (col.type === 'checkbox') {
    return (
      <span className="flex items-center gap-2 text-ui-text">
        <Checkbox id={id} checked={value === 'Yes'} onCheckedChange={(v) => onChange(v === true ? 'Yes' : 'No')} />
        {value === 'Yes' ? 'Yes' : 'No'}
      </span>
    );
  }
  if (col.type === 'select' && col.options?.length) {
    return (
      <Select value={value || undefined} onValueChange={onChange}>
        <SelectTrigger id={id}><SelectValue placeholder="Choose…" /></SelectTrigger>
        <SelectContent>
          {col.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label ?? o.value}</SelectItem>)}
        </SelectContent>
      </Select>
    );
  }
  return (
    <Input id={id} value={value} onChange={(e) => onChange(e.target.value)}
      type={col.type === 'date' ? 'date' : 'text'} inputMode={isNumeric(col.type) ? 'decimal' : undefined} />
  );
}

export interface FilterEditorProps<R = unknown> {
  columns: GridColumn<R>[];
  initial?: FilterCondition;
  submitLabel?: string;
  onSubmit: (cond: FilterCondition) => void;
  onCancel?: () => void;
  className?: string;
}

/** Edits one condition: field, operator in plain words, value. */
export function FilterEditor<R>({ columns, initial, submitLabel = 'Apply', onSubmit, onCancel, className }: FilterEditorProps<R>) {
  const [field, setField] = useState(initial?.field ?? columns[0]?.key ?? '');
  const [op, setOp] = useState<FilterOp>(initial?.op ?? 'is');
  const [value, setValue] = useState(initial?.value ?? '');
  const col = columns.find((c) => c.key === field) ?? columns[0];
  if (!col) return null;
  const ops = filterOpsFor(col.type);
  const effOp = ops.includes(op) ? op : ops[0];
  const ready = !filterNeedsValue(effOp) || col.type === 'checkbox' || value.trim() !== '';

  const pickField = (key: string) => {
    setField(key);
    setValue('');
    const next = columns.find((c) => c.key === key);
    if (next && !filterOpsFor(next.type).includes(op)) setOp(filterOpsFor(next.type)[0]);
  };

  return (
    <form data-testid="filter-editor" className={cn('space-y-3', className)}
      onSubmit={(e) => {
        e.preventDefault();
        if (!ready) return;
        const v = !filterNeedsValue(effOp) ? '' : col.type === 'checkbox' ? (value === 'Yes' ? 'Yes' : 'No') : value;
        onSubmit({ field: col.key, op: effOp, value: v });
      }}>
      <Field label="Field">
        {(p) => (
          <Select value={col.key} onValueChange={pickField}>
            <SelectTrigger id={p.id}><SelectValue /></SelectTrigger>
            <SelectContent>{columns.map((c) => <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>)}</SelectContent>
          </Select>
        )}
      </Field>
      <Field label="Condition">
        {(p) => (
          <Select value={effOp} onValueChange={(v) => setOp(v as FilterOp)}>
            <SelectTrigger id={p.id}><SelectValue /></SelectTrigger>
            <SelectContent>{ops.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
          </Select>
        )}
      </Field>
      {filterNeedsValue(effOp) && (
        <Field label="Value">{(p) => <FilterValueInput col={col} value={value} onChange={setValue} id={p.id} />}</Field>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!ready}>{submitLabel}</Button>
        {onCancel && <Button type="button" size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}

export interface FilterBuilderProps<R = unknown> {
  columns: GridColumn<R>[];
  value: FilterCondition[];
  onChange: (next: FilterCondition[]) => void;
  /** Trigger words, default "Filter". */
  addLabel?: string;
  className?: string;
}

/** "Filter" trigger + the applied conditions as chips. Drop it in GridToolbar `controls`. */
export function FilterBuilder<R>({ columns, value, onChange, addLabel = 'Filter', className }: FilterBuilderProps<R>) {
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const filterable = columns.filter((c) => c.key);
  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)} data-testid="filter-builder">
      <Popover open={adding} onOpenChange={setAdding}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5" disabled={filterable.length === 0}>
            <Plus aria-hidden="true" className="h-3.5 w-3.5" /> {addLabel}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80">
          <FilterEditor columns={filterable} submitLabel="Add filter" onCancel={() => setAdding(false)}
            onSubmit={(c) => { onChange([...value, c]); setAdding(false); }} />
        </PopoverContent>
      </Popover>
      {value.map((cond, i) => {
        const col = columns.find((c) => c.key === cond.field);
        return (
          <FilterChip key={`${cond.field}-${i}`} field={col?.label ?? cond.field} operator={cond.op} value={filterValueText(cond, col)}
            open={editing === i} onOpenChange={(o) => setEditing(o ? i : null)}
            onRemove={() => onChange(value.filter((_, k) => k !== i))}
            editor={(
              <FilterEditor columns={filterable} initial={cond} submitLabel="Update" onCancel={() => setEditing(null)}
                onSubmit={(c) => { onChange(value.map((x, k) => (k === i ? c : x))); setEditing(null); }} />
            )} />
        );
      })}
    </div>
  );
}
