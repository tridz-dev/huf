/**
 * BulkActionBar (DESIGN.md §6.11.6): floats at the bottom of the grid while
 * rows are selected. "3 rows selected · Set value · Copy · Export · Delete · ×".
 * Destructive actions sit last and always confirm. Esc clears the selection.
 */
import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface BulkAction {
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  destructive?: boolean;
  disabled?: boolean;
}

export interface BulkActionBarProps {
  count: number;
  /** Singular / plural nouns, default row / rows. */
  noun?: [string, string];
  actions: BulkAction[];
  onClear: () => void;
  /** "Select all 1,284" offer when only the page is selected. */
  selectAll?: { total: number; onClick: () => void };
  className?: string;
}

export function BulkActionBar({ count, noun = ['row', 'rows'], actions, onClear, selectAll, className }: BulkActionBarProps) {
  useEffect(() => {
    if (count === 0) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !e.defaultPrevented && onClear();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [count, onClear]);
  if (count === 0) return null;
  const ordered = [...actions.filter((a) => !a.destructive), ...actions.filter((a) => a.destructive)];
  return (
    <div role="toolbar" aria-label="Selected rows"
      className={cn('fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-1 rounded-lg bg-ink px-2 py-1.5 text-primary-foreground shadow-overlay motion-safe:animate-drop', className)}>
      <span role="status" aria-live="polite" className="px-2 text-ui-text font-medium">
        {count.toLocaleString()} {count === 1 ? noun[0] : noun[1]} selected
      </span>
      {selectAll && selectAll.total > count && (
        <Button size="sm" variant="ghost" onClick={selectAll.onClick} className="text-primary-foreground/80 hover:bg-primary-foreground/10 hover:text-primary-foreground">
          Select all {selectAll.total.toLocaleString()}
        </Button>
      )}
      <span aria-hidden="true" className="mx-1 h-4 w-px bg-primary-foreground/20" />
      {ordered.map((a) => (
        <Button key={a.label} size="sm" variant="ghost" disabled={a.disabled} onClick={a.onClick}
          className={cn('gap-1.5 hover:bg-primary-foreground/10', a.destructive ? 'text-destructive-tint hover:text-destructive-tint' : 'text-primary-foreground hover:text-primary-foreground')}>
          {a.icon}
          {a.label}
        </Button>
      ))}
      <Button size="icon-sm" variant="ghost" onClick={onClear} aria-label="Clear selection"
        className="text-primary-foreground/70 hover:bg-primary-foreground/10 hover:text-primary-foreground">
        <X aria-hidden="true" className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
