import type { ReactNode } from 'react';
import { SidebarTrigger } from '@/components/ui/sidebar';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

interface AppTopbarProps {
  /**
   * Topbar content, rendered after the sidebar trigger. Expected to be a
   * `flex-1` row so both templates align their left content identically.
   */
  children: ReactNode;
  /**
   * Suppress the bottom rule when the row directly below carries it instead
   * (a work surface's tab strip — DESIGN.md §6.5).
   */
  hideBorder?: boolean;
}

/**
 * The one topbar frame, shared by both §6.9 page templates: `UnifiedLayout`
 * (management pages) and `WorkSurfaceFrame` (work surfaces). It owns the
 * height, surface, rule, padding and the sidebar trigger + separator, so the
 * chrome is pixel-identical everywhere. What differs between templates is only
 * what goes *inside* it — a mono breadcrumb vs. a Big Shoulders bench title.
 */
export function AppTopbar({ children, hideBorder }: AppTopbarProps) {
  return (
    <header
      className={cn(
        'flex h-[60px] shrink-0 items-center gap-2 bg-panel transition-[width,height] ease-linear',
        'group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-[60px]',
        !hideBorder && 'border-b border-line',
      )}
    >
      <div className="flex w-full items-center gap-2 px-4">
        <SidebarTrigger className="-ml-1 text-steel hover:text-ink" />
        <Separator orientation="vertical" className="mr-2 h-4 bg-line" />
        {children}
      </div>
    </header>
  );
}
