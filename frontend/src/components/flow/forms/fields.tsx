import { type ReactNode, useEffect, useRef, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { Button } from '../../ui/button';
import { DataInput, type DataInputProps } from '../data/DataInput';
import { FieldHint } from '../FieldHint';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { splitDuration, toSeconds, UNIT_LABEL, type TimeUnit } from '@/lib/flow-data/flowUnits';

/** One value of a step: the data input, with the required-field message under it. */
export function ValueField({ field, f, Err, nodeId, ...rest }: { field: string; f: (field: string) => string; Err: (p: { field: string }) => ReactNode; nodeId: string } & Omit<DataInputProps, 'testId' | 'nodeId'>) {
  return (
    <div>
      <DataInput id={`field-${field.replace(/[^a-z0-9]+/gi, '-')}`} nodeId={nodeId} testId={f(field)} {...rest} />
      <Err field={field} />
    </div>
  );
}

/**
 * A waiting time with its unit: "30 [minutes]". Empty means no limit. The stored number is in seconds (or milliseconds,
 * `perUnit: 1000`); the person never sees either.
 */
export function DurationField({
  id, testId, label, hint, hintTestId, value, onChange, units, perUnit = 1, placeholder, disabled, optionalWord = true,
}: {
  id: string;
  testId: string;
  label: string;
  hint?: ReactNode;
  /** Test id of the hint, when it must keep an older name (default `<testId>-hint`). */
  hintTestId?: string;
  /** In seconds, or in milliseconds when `perUnit` is 1000. */
  value: number | undefined;
  onChange: (next: number | undefined) => void;
  units: TimeUnit[];
  perUnit?: 1 | 1000;
  placeholder?: string;
  disabled?: boolean;
  optionalWord?: boolean;
}) {
  const seconds = typeof value === 'number' ? value / perUnit : undefined;
  const initial = seconds === undefined ? { amount: undefined, unit: units[0] } : splitDuration(seconds, units);
  const [amount, setAmount] = useState<string>(initial.amount === undefined ? '' : String(initial.amount));
  const [unit, setUnit] = useState<TimeUnit>(initial.unit);
  const sent = useRef<number | undefined>(value);
  // A change from outside (undo, another tab of the form) redraws the box; our own change does not.
  useEffect(() => {
    if (value === sent.current) return;
    sent.current = value;
    const next = typeof value === 'number' ? splitDuration(value / perUnit, units) : null;
    setAmount(next ? String(next.amount) : '');
    if (next) setUnit(next.unit);
  }, [value, perUnit, units]);

  const emit = (a: string, u: TimeUnit) => {
    const n = Number(a);
    const out = a.trim() === '' || !Number.isFinite(n) || n <= 0 ? undefined : toSeconds(n, u) * perUnit;
    sent.current = out;
    onChange(out);
  };
  return (
    <div>
      <Label htmlFor={id} size="sm">{label}{optionalWord ? ' (optional)' : ''}</Label>
      <div className="flex items-center gap-2">
        <Input
          id={id}
          data-testid={testId}
          type="number"
          inputMode="decimal"
          min={1}
          className="w-24 shrink-0"
          disabled={disabled}
          value={amount}
          placeholder={placeholder ?? 'No limit'}
          onChange={(e) => { setAmount(e.target.value); emit(e.target.value, unit); }}
        />
        <Select value={unit} disabled={disabled} onValueChange={(u) => { setUnit(u as TimeUnit); emit(amount, u as TimeUnit); }}>
          <SelectTrigger className="min-w-0 flex-1" aria-label={`${label}: unit`} data-testid={`${testId}-unit`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {units.map((u) => (
              <SelectItem key={u} value={u} data-testid={`${testId}-unit-${u}`}>{UNIT_LABEL[u]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {hint ? <FieldHint testId={hintTestId ?? `${testId}-hint`}>{hint}</FieldHint> : null}
    </div>
  );
}

export type KeyValue = Record<string, unknown>;
interface Row { id: number; key: string; value: unknown }

const isPlain = (v: unknown): v is KeyValue => !!v && typeof v === 'object' && !Array.isArray(v) && !('$from' in (v as object)) && !('$template' in (v as object));

/** Can this value be shown as name / value rows? (An object whose values are text, numbers, or "use data" values.) */
export function isRowShaped(v: unknown): boolean {
  if (v === undefined || v === null || v === '') return true;
  return isPlain(v) && Object.values(v).every((x) => x === null || typeof x !== 'object' || '$from' in (x as object) || '$template' in (x as object));
}

/**
 * Name / value rows ("Authorization" / "Bearer ...") for a set of named values, each value a data input. The friendly
 * view of an object; the JSON area next to it edits the same thing.
 */
export function KeyValueRows({
  value, onChange, nodeId, testId, keyLabel = 'Name', valueLabel = 'Value', keyPlaceholder, valuePlaceholder, addLabel = 'Add another', disabled,
}: {
  value: unknown;
  onChange: (next: KeyValue | undefined) => void;
  nodeId: string;
  testId: string;
  keyLabel?: string;
  valueLabel?: string;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  addLabel?: string;
  disabled?: boolean;
}) {
  const next = useRef(1);
  const fromValue = (v: unknown): Row[] => (isPlain(v) ? Object.entries(v).map(([key, val]) => ({ id: next.current++, key, value: val })) : []);
  const [rows, setRows] = useState<Row[]>(() => fromValue(value));
  const sent = useRef(JSON.stringify(value ?? null));
  useEffect(() => {
    const now = JSON.stringify(value ?? null);
    if (now === sent.current) return;
    sent.current = now;
    setRows(fromValue(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const commit = (list: Row[]) => {
    setRows(list);
    const out: KeyValue = {};
    for (const r of list) if (r.key.trim() !== '') out[r.key.trim()] = r.value === undefined ? '' : r.value;
    const result = Object.keys(out).length ? out : undefined;
    sent.current = JSON.stringify(result ?? null);
    onChange(result);
  };
  const setRow = (id: number, p: Partial<Row>) => commit(rows.map((r) => (r.id === id ? { ...r, ...p } : r)));

  return (
    <div className="space-y-2" data-testid={testId}>
      {rows.map((r, i) => (
        <div key={r.id} className="rounded-md border border-border p-2 space-y-1.5" data-testid={`${testId}-row-${i}`}>
          <div className="flex items-end gap-2">
            <div className="min-w-0 flex-1">
              <Label htmlFor={`${testId}-key-${r.id}`} size="sm">{keyLabel}</Label>
              <Input id={`${testId}-key-${r.id}`} data-testid={`${testId}-key-${i}`} value={r.key} placeholder={keyPlaceholder} disabled={disabled} onChange={(e) => setRow(r.id, { key: e.target.value })} />
            </div>
            {!disabled && (
              <Button type="button" variant="ghost" size="sm" aria-label={`Remove ${r.key || 'this row'}`} data-testid={`${testId}-remove-${i}`} onClick={() => commit(rows.filter((x) => x.id !== r.id))}>
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
          <DataInput id={`${testId}-value-${r.id}`} nodeId={nodeId} testId={`${testId}-value-${i}`} label={valueLabel} placeholder={valuePlaceholder} value={r.value} onChange={(v) => setRow(r.id, { value: v })} />
        </div>
      ))}
      {!disabled && (
        <Button type="button" variant="outline" size="sm" className="w-full" data-testid={`${testId}-add`} onClick={() => commit([...rows, { id: next.current++, key: '', value: '' }])}>
          <Plus className="mr-1 h-3.5 w-3.5" /> {addLabel}
        </Button>
      )}
    </div>
  );
}

interface ListRow { id: number; value: unknown }

/**
 * A short list of values ("a", "b", "c") as rows with "Add" and remove, each row a data input. The friendly form of a
 * list typed as JSON. A value that is not a plain list (a whole list from an earlier step) is shown as a chip by the caller.
 */
export function ListRows({
  value, onChange, nodeId, testId, itemLabel, placeholder, addLabel, disabled,
}: {
  value: unknown;
  onChange: (next: unknown[] | undefined) => void;
  nodeId?: string;
  testId: string;
  itemLabel: string;
  placeholder?: string;
  addLabel: string;
  disabled?: boolean;
}) {
  const next = useRef(1);
  const fromValue = (v: unknown): ListRow[] => (Array.isArray(v) ? v.map((x) => ({ id: next.current++, value: x })) : []);
  const [rows, setRows] = useState<ListRow[]>(() => fromValue(value));
  const sent = useRef(JSON.stringify(value ?? null));
  useEffect(() => {
    const now = JSON.stringify(value ?? null);
    if (now === sent.current) return;
    sent.current = now;
    setRows(fromValue(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  const commit = (list: ListRow[]) => {
    setRows(list);
    const out = list.map((r) => r.value).filter((v) => !(v === '' || v === undefined));
    const result = out.length ? out : undefined;
    sent.current = JSON.stringify(result ?? null);
    onChange(result);
  };
  return (
    <div className="space-y-2" data-testid={testId}>
      {rows.map((r, i) => (
        <div key={r.id} className="flex items-start gap-2" data-testid={`${testId}-row-${i}`}>
          <div className="min-w-0 flex-1">
            <DataInput id={`${testId}-item-${r.id}`} nodeId={nodeId} testId={`${testId}-item-${i}`} label={`${itemLabel} ${i + 1}`} placeholder={placeholder} value={r.value} onChange={(v) => commit(rows.map((x) => (x.id === r.id ? { ...x, value: v } : x)))} />
          </div>
          {!disabled && (
            <Button type="button" variant="ghost" size="sm" className="mt-6" aria-label={`Remove ${itemLabel.toLowerCase()} ${i + 1}`} data-testid={`${testId}-remove-${i}`} onClick={() => commit(rows.filter((x) => x.id !== r.id))}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      ))}
      {!disabled && (
        <Button type="button" variant="outline" size="sm" className="w-full" data-testid={`${testId}-add`} onClick={() => setRows([...rows, { id: next.current++, value: '' }])}>
          <Plus className="mr-1 h-3.5 w-3.5" /> {addLabel}
        </Button>
      )}
    </div>
  );
}
