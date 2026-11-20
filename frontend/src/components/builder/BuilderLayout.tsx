/**
 * BuilderLayout (DESIGN.md §6.12.1): configure on the left, try on the right.
 * A main column (head, tabs, sections) plus a sticky side panel that stays in
 * view while the main column scrolls. Below `lg` the panel stacks under the
 * main column (or the caller moves it into a sheet).
 */
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface BuilderLayoutProps {
  children: ReactNode;
  /** Side panel, usually a TryPanel or a live preview. */
  aside?: ReactNode;
  /** Accessible name for the side panel region. */
  asideLabel?: string;
  /** `md` = 400px panel (default), `lg` = 480px. */
  asideSize?: 'md' | 'lg';
  className?: string;
}

export function BuilderLayout({ children, aside, asideLabel = 'Preview', asideSize = 'md', className }: BuilderLayoutProps) {
  return (
    <div className={cn('grid gap-6', aside && (asideSize === 'lg' ? 'lg:grid-cols-[minmax(0,1fr)_480px]' : 'lg:grid-cols-[minmax(0,1fr)_400px]'), className)}>
      <div className="min-w-0 space-y-5">{children}</div>
      {aside && (
        <aside aria-label={asideLabel} className="min-w-0 lg:sticky lg:top-4 lg:h-[calc(100vh-6rem)] lg:self-start">
          {aside}
        </aside>
      )}
    </div>
  );
}
