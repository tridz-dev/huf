/**
 * ColumnTypePicker / ColumnTypeList (DESIGN.md §6.11.2): choose a field type
 * by meaning. Each option = icon + user word + one-line description, grouped
 * and searchable. Defaults to the grid's ColumnTypes; callers with a wider
 * vocabulary (rating, phone, layout breaks…) pass their own `options`.
 */
import { useState, type KeyboardEvent, type ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { TYPE_DESCRIPTION, TYPE_ICON, TYPE_LABEL, type ColumnType } from './types';

export interface ColumnTypeOption<T extends string = string> {
  value: T;
  label: string;
  description?: string;
  icon?: LucideIcon;
  /** Group heading, e.g. "Numbers". Options keep their given order. */
  group?: string;
}

const GROUP: Record<ColumnType, string> = {
  text: 'Text', longtext: 'Text', number: 'Numbers', currency: 'Numbers',
  date: 'Date', select: 'Choice', checkbox: 'Choice', link: 'Reference',
};

/** The grid's own types as picker options (all, or the listed ones in order). */
export function gridTypeOptions(types: ColumnType[] = Object.keys(TYPE_LABEL) as ColumnType[]): ColumnTypeOption<ColumnType>[] {
  return types.map((t) => ({ value: t, label: TYPE_LABEL[t], description: TYPE_DESCRIPTION[t], icon: TYPE_ICON[t], group: GROUP[t] }));
}

export interface ColumnTypeListProps<T extends string> {
  options: ColumnTypeOption<T>[];
  value?: T;
  onSelect: (value: T) => void;
  /** Show a search box above the list (on by default above 8 options). */
  searchable?: boolean;
  label?: string;
  className?: string;
}

/** Inline list (use inside a sheet or a create form). */
export function ColumnTypeList<T extends string>({ options, value, onSelect, searchable, label = 'Field type', className }: ColumnTypeListProps<T>) {
  const [q, setQ] = useState('');
  const query = q.trim().toLowerCase();
  const shown = query
    ? options.filter((o) => `${o.label} ${o.description ?? ''} ${o.group ?? ''}`.toLowerCase().includes(query))
    : options;
  const groups: { name?: string; items: ColumnTypeOption<T>[] }[] = [];
  for (const o of shown) {
    const g = groups.find((x) => x.name === o.group);
    g ? g.items.push(o) : groups.push({ name: o.group, items: [o] });
  }
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="option"]'));
    const i = items.indexOf(document.activeElement as HTMLElement);
    e.preventDefault();
    items[Math.max(0, Math.min(items.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]?.focus();
  };
  return (
    <div className={cn('space-y-2', className)} onKeyDown={onKey}>
      {(searchable ?? options.length > 8) && (
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search types…" aria-label="Search field types" />
      )}
      <div role="listbox" aria-label={label} className="max-h-80 space-y-2 overflow-y-auto">
        {groups.length === 0 && <p className="px-2 py-3 text-micro text-steel">No type matches “{q}”.</p>}
        {groups.map((g) => (
          <div key={g.name ?? '_'} role="group" aria-label={g.name}>
            {g.name && <p aria-hidden="true" className="px-2 pb-1 text-meta text-steel-soft">{g.name}</p>}
            {g.items.map((o) => {
              const Icon = o.icon;
              const on = o.value === value;
              return (
                <button key={o.value} type="button" role="option" aria-selected={on} onClick={() => onSelect(o.value)}
                  className={cn('flex w-full items-start gap-2.5 rounded-md px-2 py-1.5 text-left hover:bg-paper-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    on && 'bg-signal/5')}>
                  {Icon && <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-steel" />}
                  <span className="min-w-0">
                    <span className="block text-ui-text text-ink">{o.label}</span>
                    {o.description && <span className="block text-micro text-steel">{o.description}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export interface ColumnTypePickerProps<T extends string = ColumnType> extends Omit<ColumnTypeListProps<T>, 'options' | 'className'> {
  /** Defaults to gridTypeOptions(). */
  options?: ColumnTypeOption<T>[];
  /** Trigger element (a Button). */
  trigger: ReactNode;
  align?: 'start' | 'center' | 'end';
}

/** Popover form: trigger → searchable, grouped type list. Closes on pick. */
export function ColumnTypePicker<T extends string = ColumnType>({ options, trigger, onSelect, align = 'start', ...rest }: ColumnTypePickerProps<T>) {
  const [open, setOpen] = useState(false);
  const opts = options ?? (gridTypeOptions() as unknown as ColumnTypeOption<T>[]);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent align={align} className="w-80 p-2">
        <ColumnTypeList {...rest} options={opts} onSelect={(v) => { setOpen(false); onSelect(v); }} />
      </PopoverContent>
    </Popover>
  );
}
