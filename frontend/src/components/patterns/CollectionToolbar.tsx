/**
 * CollectionToolbar (DESIGN.md §6.10.3): the band between the page head and
 * the list. Row 1 is the ask/search field; row 2 holds the filter pills on
 * the left and an optional view control (sort, density) on the right.
 */
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface CollectionToolbarProps {
  /** Usually an <AskField>. */
  search: ReactNode;
  /** Usually <FilterPills>. Hidden while a search is showing results. */
  filters?: ReactNode;
  /** Right-aligned extra control on the filter row. */
  trailing?: ReactNode;
  className?: string;
}

export function CollectionToolbar({ search, filters, trailing, className }: CollectionToolbarProps) {
  return (
    <div className={cn('flex flex-col gap-3', className)} data-testid="collection-toolbar">
      {search}
      {(filters || trailing) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">{filters}</div>
          {trailing && <div className="flex shrink-0 items-center gap-2">{trailing}</div>}
        </div>
      )}
    </div>
  );
}
