import { useLayoutEffect, type ReactNode, type RefObject } from 'react';
import { cn } from '@/lib/utils';
import { usePageChrome } from './UnifiedLayout';

interface PageFrameProps {
  /** Page-head title — apple-quiet system font, sentence case h1. Named once, here. */
  title?: ReactNode;
  /** Optional pill next to the title (e.g. EXPERIMENTAL). */
  badge?: ReactNode;
  /**
   * Inline meta next to the title — a count, a status, a last-run stamp.
   * Lives in the same 52px bar as the title, never a second stat row.
   * e.g. `meta="24 agents"` or `meta="Last run never · 0 runs"`.
   */
  meta?: ReactNode;
  /** Right side of the page head — the primary action, plus any secondary cluster. */
  actions?: ReactNode;
  /**
   * Optional tab/filter row directly under the head. Counted against the
   * 92px total page-chrome budget, so keep it to a single dense row.
   */
  filters?: ReactNode;
  children: ReactNode;
  className?: string;
  scrollRef?: RefObject<HTMLDivElement>;
}

/**
 * Management-page template (Dashboard, Agents, Executions): a single 52px
 * head bar — sentence-case h1, optional badge, inline meta, primary action —
 * with an optional tab/filter row beneath it. Total page chrome (head + tab
 * row) never exceeds 92px, and there is no subtitle band: purpose copy that
 * used to live in a second line belongs in the meta slot, a tooltip, or the
 * empty state, not a permanent band under the title.
 *
 * The title lives here, never in the global topbar.
 */
export function PageFrame({
  title,
  badge,
  meta,
  actions,
  filters,
  children,
  className,
  scrollRef,
}: PageFrameProps) {
  const chrome = usePageChrome();
  // A head bar only exists when there's a title or actions to show — an
  // empty PageFrame renders no bar at all, so it must not claim the rail
  // toggle (see UnifiedLayout's PageChromeContext doc comment).
  const showHeadBar = Boolean(title || actions);

  useLayoutEffect(() => {
    if (!chrome) return;
    chrome.setFramed(showHeadBar);
    return () => chrome.setFramed(false);
  }, [chrome, showHeadBar]);

  return (
    <div ref={scrollRef} className="h-full overflow-auto">
      <div className={cn('flex flex-col', className)}>
        {showHeadBar && (
          <div className="h-[52px] shrink-0 flex items-center justify-between gap-4 px-6">
            <div className="flex items-center gap-3 min-w-0">
              {chrome && (
                <>
                  {chrome.railToggle}
                  {chrome.ancestryCrumb}
                </>
              )}
              {title && (
                <h1 className="font-display text-title text-ink leading-none truncate">
                  {title}
                </h1>
              )}
              {badge}
              {meta && (
                <span className="font-body text-meta text-steel truncate">{meta}</span>
              )}
            </div>
            {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
          </div>
        )}

        {filters && (
          <div className="h-10 shrink-0 flex items-center border-b border-line px-6">
            {filters}
          </div>
        )}

        <div className="flex-1 p-6">{children}</div>
      </div>
    </div>
  );
}
