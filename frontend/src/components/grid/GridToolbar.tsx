/**
 * GridToolbar (DESIGN.md §6.11.5): the row above a DataGrid.
 * [search] [Filter] [Sort] [Fields] [applied chips…]  ·  [match count] [save status]
 * Plus MatchCount, FieldsMenu and GridFooter, which share its vocabulary.
 */
import type { ReactNode } from 'react';
import { EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ShortcutKey } from '@/components/ui/shortcut-key';
import { cn } from '@/lib/utils';

export interface GridToolbarProps {
  /** Usually an AskField from `@/components/patterns`. */
  search?: ReactNode;
  /** Filter / Sort / Fields triggers. */
  controls?: ReactNode;
  /** Applied FilterChip / SortChip list. */
  chips?: ReactNode;
  /** MatchCount and AutosaveStatus, right-aligned. */
  end?: ReactNode;
  className?: string;
}

export function GridToolbar({ search, controls, chips, end, className }: GridToolbarProps) {
  return (
    <div role="toolbar" aria-label="Grid tools" className={cn('flex flex-wrap items-center gap-2 py-3', className)}>
      {search && <div className="w-full sm:w-64">{search}</div>}
      {controls}
      {chips && <div className="flex flex-wrap items-center gap-1.5">{chips}</div>}
      {end && <div className="ml-auto flex items-center gap-3 text-micro text-steel">{end}</div>}
    </div>
  );
}

/** "212 of 1,284 rows" while filtered, "1,284 rows" otherwise. Polite live region. */
export function MatchCount({ shown, total, noun = 'rows', className }: { shown: number; total: number; noun?: string; className?: string }) {
  return (
    <span role="status" aria-live="polite" data-testid="match-count" className={cn('font-mono text-meta text-steel', className)}>
      {shown === total ? `${total.toLocaleString()} ${noun}` : `${shown.toLocaleString()} of ${total.toLocaleString()} ${noun}`}
    </span>
  );
}

export interface FieldsMenuProps {
  fields: { key: string; label: string; locked?: boolean }[];
  hidden: ReadonlySet<string>;
  onHiddenChange: (next: Set<string>) => void;
}

/** Show/hide columns. A `locked` field (the title) can't be hidden. */
export function FieldsMenu({ fields, hidden, onHiddenChange }: FieldsMenuProps) {
  const set = (key: string, show: boolean) => {
    const next = new Set(hidden);
    show ? next.delete(key) : next.add(key);
    onHiddenChange(next);
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <EyeOff aria-hidden="true" className="h-3.5 w-3.5" />
          Fields{hidden.size > 0 && <span className="font-mono text-meta text-steel">{hidden.size} hidden</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Show fields</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {fields.map((f) => (
          <DropdownMenuCheckboxItem key={f.key} checked={!hidden.has(f.key)} disabled={f.locked}
            onCheckedChange={(v) => set(f.key, v === true)} onSelect={(e) => e.preventDefault()}>
            {f.label}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** "Showing 1–25 of 1,284 rows" + the keyboard legend. */
export function GridFooter({ from, to, total, noun = 'rows', pager, className }: {
  from: number; to: number; total: number; noun?: string; pager?: ReactNode; className?: string;
}) {
  return (
    <div className={cn('flex flex-wrap items-center gap-3 py-2 text-micro text-steel', className)}>
      <span>{total === 0 ? `No ${noun}` : `Showing ${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()} ${noun}`}</span>
      {pager}
      <span className="ml-auto hidden items-center gap-3 md:flex" aria-hidden="true">
        <span className="inline-flex items-center gap-1"><ShortcutKey size="sm">Tab</ShortcutKey> next</span>
        <span className="inline-flex items-center gap-1"><ShortcutKey size="sm">Enter</ShortcutKey> save</span>
        <span className="inline-flex items-center gap-1"><ShortcutKey size="sm">Esc</ShortcutKey> cancel</span>
        <span className="inline-flex items-center gap-1"><ShortcutKey size="sm" keys={['⌘', 'V']} /> paste rows</span>
      </span>
    </div>
  );
}
