import type { ReactNode, RefObject } from 'react';
import { cn } from '@/lib/utils';

interface PageFrameProps {
  /** Page-head title — apple-quiet system font, sentence case h1. */
  title?: ReactNode;
  /** Optional pill next to the title (e.g. EXPERIMENTAL). */
  badge?: ReactNode;
  /** Optional steel sentence-case subtitle. */
  subtitle?: string;
  /** Right side of the page head. */
  actions?: ReactNode;
  /** Optional filter row between the head and the content. */
  filters?: ReactNode;
  children: ReactNode;
  className?: string;
  scrollRef?: RefObject<HTMLDivElement>;
}

/**
 * Management-page template (Dashboard, Agents, Executions): page head
 * (sentence-case h1 + steel subtitle + optional actions) above the content
 * column. The title lives here, never in the global topbar.
 */
export function PageFrame({
  title,
  badge,
  subtitle,
  actions,
  filters,
  children,
  className,
  scrollRef,
}: PageFrameProps) {
  return (
    <div ref={scrollRef} className="h-full overflow-auto">
      <div className={cn('p-6 space-y-6', className)}>
        {(title || subtitle || actions || filters) && (
          <div className="space-y-4">
            {(title || subtitle || actions) && (
              <div className="flex items-end justify-between gap-4">
                <div className="space-y-1">
                  {title && (
                    <div className="flex items-center gap-3">
                      <h1 className="font-display text-title text-ink leading-tight">
                        {title}
                      </h1>
                      {badge}
                    </div>
                  )}
                  {subtitle && (
                    <p className="font-body text-steel text-[14.5px]">{subtitle}</p>
                  )}
                </div>
                {actions && <div className="flex items-center gap-2">{actions}</div>}
              </div>
            )}

            {filters && <div>{filters}</div>}
          </div>
        )}

        <div>{children}</div>
      </div>
    </div>
  );
}
