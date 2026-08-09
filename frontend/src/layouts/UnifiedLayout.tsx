import { ReactNode, createContext, useContext, useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AppSidebar } from '../components/app-sidebar';
import { UnifiedHeader, AncestryCrumb } from './UnifiedHeader';
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from '../components/ui/sidebar';
import { Separator } from '../components/ui/separator';
import { ShortcutsHelpProvider } from '../components/shortcuts/ShortcutsHelpContext';
import { cn } from '../lib/utils';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface UnifiedLayoutProps {
  children?: ReactNode;
  sidebarContent?: ReactNode;
  hideHeader?: boolean;
  headerActions?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  /**
   * Replaces the ancestry-crumb/page-title zone on the left of the header
   * with custom content (e.g. a "Flows > name [edit]" control). Falls back
   * to the default AncestryCrumb/title rendering when omitted.
   */
  leftContent?: ReactNode;
  /**
   * Renders the standalone topbar at a denser 46px instead of the default
   * 60px, keeping the same bottom hairline. Intended for the flow canvas
   * toolbar only — leave unset everywhere else.
   */
  compact?: boolean;
  /**
   * Opt-in: also render the trailing/current-page crumb (plus a leading
   * back-arrow icon) instead of only the ancestor chain. Use this for pages
   * that don't otherwise render their own name anywhere in the content
   * column — e.g. a run-detail page whose back-navigation lives entirely in
   * this breadcrumb. See AncestryCrumb in UnifiedHeader.tsx for details.
   */
  showCurrentCrumb?: boolean;
}

/**
 * Page chrome shared between the standalone 60px topbar and PageFrame's own
 * 52px head bar, so the rail toggle (and, on nested routes, the ancestry
 * breadcrumb) is reachable exactly once no matter which one is on screen.
 *
 * PageFrame calls `setFramed(true)` while its own head bar is rendering its
 * title, which tells UnifiedLayout to stop rendering the standalone topbar
 * (avoiding a duplicated page name and a duplicated primary action) and
 * instead hands the rail toggle + ancestry breadcrumb to PageFrame to render
 * inline. Pages that never mount a PageFrame head bar (or set title/actions
 * to nothing) never call setFramed, so the topbar — and the toggle it
 * carries — stays put. That keeps the toggle reachable everywhere.
 */
interface PageChromeContextValue {
  railToggle: ReactNode;
  ancestryCrumb: ReactNode;
  setFramed: (framed: boolean) => void;
}

const PageChromeContext = createContext<PageChromeContextValue | null>(null);

export function usePageChrome() {
  return useContext(PageChromeContext);
}

export function UnifiedLayout({ children, hideHeader, headerActions, breadcrumbs, leftContent, compact, showCurrentCrumb }: UnifiedLayoutProps) {
  const location = useLocation();
  const defaultOpen = location.pathname !== '/';
  const [framed, setFramed] = useState(false);

  const railToggle = useMemo(
    () => (
      <>
        <SidebarTrigger className="-ml-1 text-steel hover:text-ink" />
        <Separator orientation="vertical" className="h-4 bg-line" />
      </>
    ),
    [],
  );

  const ancestryCrumb = useMemo(
    () => <AncestryCrumb breadcrumbs={breadcrumbs} showCurrentCrumb={showCurrentCrumb} />,
    [breadcrumbs, showCurrentCrumb],
  );

  const chromeValue = useMemo<PageChromeContextValue>(
    () => ({ railToggle, ancestryCrumb, setFramed }),
    [railToggle, ancestryCrumb],
  );

  return (
    <ShortcutsHelpProvider>
      <SidebarProvider defaultOpen={defaultOpen}>
        <AppSidebar />
        <SidebarInset className="h-svh max-h-svh overflow-hidden">
          {!hideHeader && !framed && (
            <header
              className={cn(
                'flex shrink-0 items-center gap-2 transition-[width,height] ease-linear border-b border-line bg-panel',
                compact
                  ? 'h-[46px] group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-[46px]'
                  : 'h-[60px] group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-[60px]',
              )}
            >
              <div className="flex items-center gap-2 px-4 w-full">
                <SidebarTrigger className="-ml-1 text-steel hover:text-ink" />
                <Separator orientation="vertical" className="mr-2 h-4 bg-line" />
                <UnifiedHeader
                  actions={headerActions}
                  breadcrumbs={breadcrumbs}
                  leftContent={leftContent}
                  showCurrentCrumb={showCurrentCrumb}
                />
              </div>
            </header>
          )}
          <main className="flex-1 overflow-hidden flex flex-col min-h-0">
            {hideHeader ? (
              children || <Outlet />
            ) : (
              <PageChromeContext.Provider value={chromeValue}>
                {children || <Outlet />}
              </PageChromeContext.Provider>
            )}
          </main>
        </SidebarInset>
      </SidebarProvider>
    </ShortcutsHelpProvider>
  );
}
