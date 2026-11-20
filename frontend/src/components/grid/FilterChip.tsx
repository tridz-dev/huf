/**
 * FilterChip and SortChip (DESIGN.md §6.11.5): one applied condition each,
 * read as a sentence ("Status is Active"). The body opens its editor (an
 * optional popover); the × removes it. Backspace / Delete on a focused chip
 * also removes it, like a token in a search field.
 */
import type { KeyboardEvent, ReactNode } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, X } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { sortDirectionLabel, type ColumnType, type SortDirection } from './types';

const CHIP = 'inline-flex h-control-sm items-center rounded-full border border-signal/30 bg-signal/5 text-micro text-ink';
const PART = 'inline-flex h-full items-center gap-1 rounded-full px-3 hover:bg-signal/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

export interface FilterChipProps {
  field: string;
  /** Plain operator words: "is", "is not", "contains", "is before", "is empty". */
  operator: string;
  value?: ReactNode;
  onRemove: () => void;
  /** Popover body that edits this condition. */
  editor?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

export function FilterChip({ field, operator, value, onRemove, editor, open, onOpenChange, className }: FilterChipProps) {
  const sentence = `${field} ${operator}${value !== undefined && typeof value !== 'object' ? ` ${value}` : ''}`;
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Backspace' || e.key === 'Delete') {
      e.preventDefault();
      onRemove();
    }
  };
  const body = (
    <button type="button" className={PART} onKeyDown={onKey} aria-label={`Filter: ${sentence}`}>
      <span className="text-steel">{field}</span>
      <span className="text-steel-soft">{operator}</span>
      {value !== undefined && <span className="font-medium">{value}</span>}
    </button>
  );
  return (
    <span data-testid="filter-chip" className={cn(CHIP, className)}>
      {editor ? (
        <Popover open={open} onOpenChange={onOpenChange}>
          <PopoverTrigger asChild>{body}</PopoverTrigger>
          <PopoverContent align="start" className="w-80">{editor}</PopoverContent>
        </Popover>
      ) : body}
      <button type="button" onClick={onRemove} aria-label={`Remove filter ${sentence}`}
        className="mr-1 inline-flex h-5 w-5 items-center justify-center rounded-full text-steel hover:bg-signal/10 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <X aria-hidden="true" className="h-3 w-3" />
      </button>
    </span>
  );
}

export interface SortChipProps {
  field: string;
  direction: 'asc' | 'desc';
  onToggle: () => void;
  onRemove: () => void;
  /** Type-aware words; defaults to A→Z / Z→A. Use "Oldest first" for dates, "1→9" for numbers. */
  directionLabel?: string;
  className?: string;
}

export function SortChip({ field, direction, onToggle, onRemove, directionLabel, className }: SortChipProps) {
  const Icon = direction === 'asc' ? ArrowUp : ArrowDown;
  const words = directionLabel ?? (direction === 'asc' ? 'A→Z' : 'Z→A');
  return (
    <span data-testid="sort-chip" className={cn(CHIP, className)}>
      <button type="button" className={PART} onClick={onToggle} aria-label={`Sorted by ${field}, ${words}. Reverse`}>
        <Icon aria-hidden="true" className="h-3 w-3 text-steel" />
        <span>{field}</span>
        <span className="text-steel-soft">{words}</span>
      </button>
      <button type="button" onClick={onRemove} aria-label={`Remove sort by ${field}`}
        className="mr-1 inline-flex h-5 w-5 items-center justify-center rounded-full text-steel hover:bg-signal/10 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <X aria-hidden="true" className="h-3 w-3" />
      </button>
    </span>
  );
}

/**
 * SortHeaderButton: the clickable DataGrid column header. Click / Enter /
 * Space cycles none → asc → desc → none (nextSort); the owning <th> carries
 * aria-sort. Same direction words as SortChip (sortDirectionLabel).
 */
export function ariaSort(direction: SortDirection | undefined): 'ascending' | 'descending' | 'none' {
  return direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none';
}

export function SortHeaderButton({ label, type, direction, onClick, children, className }: {
  label: string; type: ColumnType; direction?: SortDirection; onClick: () => void; children: ReactNode; className?: string;
}) {
  const Icon = direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ArrowUpDown;
  const now = direction ? `sorted ${sortDirectionLabel(type, direction)}` : 'not sorted';
  const next = !direction ? sortDirectionLabel(type, 'asc') : direction === 'asc' ? sortDirectionLabel(type, 'desc') : 'no sort';
  return (
    <button type="button" onClick={onClick} aria-label={`${label}, ${now}. Sort ${next}`}
      className={cn('group/sort flex w-full min-w-0 items-center gap-1.5 rounded text-left hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', className)}>
      {children}
      <Icon aria-hidden="true" data-testid="sort-icon"
        className={cn('h-3 w-3 shrink-0', direction ? 'text-signal' : 'text-steel-soft opacity-0 group-hover/sort:opacity-100 group-focus-visible/sort:opacity-100')} />
    </button>
  );
}
