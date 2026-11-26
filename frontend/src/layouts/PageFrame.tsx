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
  /** Tabs of a page that hosts several lists (Executions): a row directly under the title, above the filters. */
  tabs?: ReactNode;
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
  tabs,
  children,
  className,
  scrollRef,
}: PageFrameProps) {
  const chrome = usePageChrome();
  // A head bar only exists when there's a title or actions to show — an
  // empty PageFrame renders no bar at all, so it must not claim the rail
  // toggle (see UnifiedLayout's PageChromeContext doc comment).
  const showHeadBar = Boolean(title || actions);
  // This bar replaces the topbar, so it carries what the topbar would have shown.
  const headActions = actions ?? chrome?.headerActions;

  useLayoutEffect(() => {
    if (!chrome) return;
    chrome.setFramed(showHeadBar);
    return () => chrome.setFramed(false);
  }, [chrome, showHeadBar]);

  return (
    <div ref={scrollRef} className="h-full overflow-auto">
      <div className={cn('flex flex-col', className)}>
        {/* On phones the actions take their own row, so the title, toggle and bells stay visible. */}
        {showHeadBar && (
          <div className="h-[52px] shrink-0 flex items-center justify-between gap-4 px-6 max-sm:h-auto max-sm:min-h-[52px] max-sm:flex-wrap max-sm:gap-2 max-sm:py-2">
            <div className="flex items-center gap-3 min-w-0 max-sm:flex-1 max-sm:flex-wrap max-sm:gap-y-1">
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
            {(chrome || headActions) && (
              <div className="flex items-center gap-2 shrink-0 max-sm:contents">
                {chrome?.approvals}
                {headActions && (
                  <div className="flex items-center gap-2 empty:hidden max-sm:w-full max-sm:flex-wrap max-sm:[&>div]:flex-wrap">
                    {headActions}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {tabs && (
          <div className={cn('shrink-0 flex flex-wrap items-center gap-x-4 gap-y-1 px-6 pb-1', !filters && 'border-b border-line')} data-testid="page-frame-tabs">
            {tabs}
          </div>
        )}

        {filters && (
          <div className="min-h-10 shrink-0 flex items-stretch border-b border-line px-6 max-sm:py-1">
            {filters}
          </div>
        )}

        <div className="flex-1 p-6">{children}</div>
      </div>
    </div>
  );
}
