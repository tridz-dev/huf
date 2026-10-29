import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { PanelLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SidebarProvider, useSidebar } from '@/components/ui/sidebar';
import { cn } from '@/lib/utils';

/** Below this width the rail becomes an overlay behind a hamburger. */
export const APP_SHELL_MOBILE_BREAKPOINT = 900;

const isNarrow = () => typeof window !== 'undefined' && window.innerWidth < APP_SHELL_MOBILE_BREAKPOINT;

function useIsNarrow() {
  const [narrow, setNarrow] = useState(isNarrow);
  useEffect(() => {
    const onResize = () => setNarrow(isNarrow());
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return narrow;
}

export interface AppShellFrameProps {
  /** Rail content (rendered inside a 248px column, or an overlay when narrow). */
  rail: ReactNode;
  /** Topbar content, placed after the sidebar trigger in the 60px bar. */
  topbar?: ReactNode;
  children: ReactNode;
}

function ShellBody({ rail, topbar, children }: AppShellFrameProps) {
  const narrow = useIsNarrow();
  const { open, setOpen } = useSidebar();

  // Narrow viewports start with the rail closed; wide ones open.
  useEffect(() => {
    setOpen(!narrow);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [narrow]);

  const toggle = useCallback(() => setOpen(!open), [open, setOpen]);

  return (
    <section className="relative flex h-full w-full overflow-hidden bg-paper text-ink">
      {narrow ? (
        open && (
          <>
            <button
              type="button"
              aria-label="Close menu"
              className="absolute inset-0 z-30 bg-ink/40"
              onClick={() => setOpen(false)}
            />
            <div data-testid="app-shell-rail" className="absolute inset-y-0 left-0 z-40 w-[248px] border-r border-line bg-sidebar">
              {rail}
            </div>
          </>
        )
      ) : (
        <div
          data-testid="app-shell-rail"
          className={cn(
            'shrink-0 overflow-hidden border-line bg-sidebar transition-all duration-200 ease-in-out',
            open ? 'w-[248px] border-r' : 'w-0'
          )}
        >
          {rail}
        </div>
      )}

      <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-[60px] shrink-0 items-center gap-3 border-b border-line bg-panel px-4">
          <Button
            variant="ghost"
            size="icon"
            data-sidebar="trigger"
            className="h-7 w-7 text-steel hover:bg-transparent hover:text-ink"
            onClick={toggle}
          >
            <PanelLeft />
            <span className="sr-only">Toggle sidebar</span>
          </Button>
          <div className="min-w-0 flex-1">{topbar}</div>
        </header>
        <main className="min-h-0 flex-1 overflow-auto">{children}</main>
      </div>
    </section>
  );
}

/**
 * Reusable full-screen app shell (generalised from ChatShellFrame +
 * WorkSurfaceFrame): own SidebarProvider, 248px rail, overlay under 900px,
 * 60px topbar with the sidebar trigger. Mount outside UnifiedLayout.
 */
export function AppShellFrame(props: AppShellFrameProps) {
  return (
    <SidebarProvider className="h-svh min-h-0">
      <ShellBody {...props} />
    </SidebarProvider>
  );
}
