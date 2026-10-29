import { useMemo, useState } from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';
import { Button } from '../ui/button';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '../ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { cn } from '@/lib/utils';
import { filterDoctypes } from '@/lib/flow-graph/flowTrigger';
import type { TriggerDoctype } from '@/services/flow/triggerApi';

const GROUP_TITLE: Record<TriggerDoctype['group'], string> = {
  common: 'Everyday records',
  yours: 'Your tables',
  apps: 'From your apps',
};
const MAX_SHOWN = 120;

interface Props {
  id?: string;
  testId: string;
  options: TriggerDoctype[];
  /** The chosen document type's name (not its label). */
  value: string;
  onChange: (name: string) => void;
  /** Called when the list closes, with whether something is chosen (so an untouched form never shows an error). */
  onClosed?: (hasValue: boolean) => void;
  loading?: boolean;
  disabled?: boolean;
}

/** Searchable, grouped list of the document types a trigger can watch. Shows what people call each one, not its internal name. */
export function DoctypePicker({ id, testId, options, value, onChange, onClosed, loading, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const selected = options.find((o) => o.name === value);
  const shown = useMemo(() => filterDoctypes(options, query).slice(0, MAX_SHOWN), [options, query]);
  const groups = (['common', 'yours', 'apps'] as const).map((g) => ({ g, items: shown.filter((d) => d.group === g) })).filter((x) => x.items.length > 0);
  // Ranked results read as one list; the groups only help while browsing.
  const flat = query.trim() !== '';

  const row = (d: TriggerDoctype) => (
    <CommandItem
      key={d.name}
      value={d.name}
      data-testid={`${testId}-option-${d.name}`}
      onSelect={() => {
        onChange(d.name);
        setOpen(false);
      }}
    >
      <Check className={cn('mr-2 h-4 w-4 shrink-0', value === d.name ? 'opacity-100' : 'opacity-0')} />
      <span className="min-w-0 flex-1 truncate">{d.label}</span>
      {d.group === 'apps' && d.module ? <span className="ml-2 shrink-0 text-xs text-muted-foreground">{d.module}</span> : null}
    </CommandItem>
  );

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setQuery('');
          onClosed?.(Boolean(value));
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled || loading}
          data-testid={testId}
          className="w-full justify-between bg-transparent font-normal"
        >
          <span className={cn('min-w-0 flex-1 truncate text-left', !selected && !value && 'text-muted-foreground')}>
            {loading ? 'Loading...' : selected?.label ?? (value || 'choose a kind of record')}
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] min-w-64 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search document types" value={query} onValueChange={setQuery} data-testid={`${testId}-search`} />
          <CommandList>
            <CommandEmpty>{options.length ? 'Nothing matches that. Try a shorter word.' : 'No document types are available to your account.'}</CommandEmpty>
            {flat ? (
              <CommandGroup>{shown.map(row)}</CommandGroup>
            ) : (
              groups.map(({ g, items }) => (
                <CommandGroup key={g} heading={GROUP_TITLE[g]}>
                  {items.map(row)}
                </CommandGroup>
              ))
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
