import { useCallback, useEffect, useState } from 'react';
import { PanelLeftOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useIsMobile } from '@/hooks/use-mobile';
import { ChatRail } from './ChatRail';

export interface ChatShellFrameProps {
  children: React.ReactNode;
  rightPane?: React.ReactNode;
  // Controlled sidebar state, for callers (like ChatPageV2) that need to
  // react to selection changes on top of the shared open/collapsed
  // behaviour - e.g. closing the rail on mobile once a conversation is
  // picked, or wiring a header toggle button. Uncontrolled callers (the
  // placeholder pages) omit these and get sensible defaults on their own.
  sidebarOpen?: boolean;
  onToggleSidebar?: () => void;
}

// Shared shell for every /chat* route: owns the rail's open/collapsed and
// mobile-overlay behaviour so it renders consistently on the conversation
// view (ChatPageV2) and on the Projects/Artifacts/Scheduled placeholder
// pages alike - none of those routes should be a navigation dead-end.
export function ChatShellFrame({
  children,
  rightPane,
  sidebarOpen: controlledSidebarOpen,
  onToggleSidebar: controlledToggleSidebar,
}: ChatShellFrameProps) {
  const isMobile = useIsMobile();
  const [internalSidebarOpen, setInternalSidebarOpen] = useState(true);
  const toggleInternalSidebar = useCallback(() => setInternalSidebarOpen((prev) => !prev), []);

  // Auto-close sidebar on mobile, auto-open on desktop. Only meaningful for
  // the uncontrolled case - controlled callers run this themselves.
  useEffect(() => {
    setInternalSidebarOpen(!isMobile);
  }, [isMobile]);

  const isControlled = controlledSidebarOpen !== undefined;
  const sidebarOpen = isControlled ? controlledSidebarOpen : internalSidebarOpen;
  const toggleSidebar = isControlled ? (controlledToggleSidebar ?? toggleInternalSidebar) : toggleInternalSidebar;

  return (
    <section className="flex h-full overflow-hidden relative">
      {/* Sidebar - overlay on mobile, inline on desktop */}
      {isMobile ? (
        sidebarOpen && (
          <div className="absolute inset-0 z-30 bg-sidebar">
            <ChatRail onToggleRail={toggleSidebar} />
          </div>
        )
      ) : (
        <div
          className={cn(
            'shrink-0 transition-all duration-200 ease-in-out overflow-hidden',
            sidebarOpen ? 'w-chat-rail' : 'w-0'
          )}
        >
          <ChatRail onToggleRail={toggleSidebar} />
        </div>
      )}

      <div className="flex-1 min-w-0 min-h-0 h-full relative">
        {/* Desktop-only floating toggle */}
        {!isMobile && !sidebarOpen && (
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleSidebar}
            className="absolute top-4 left-4 z-20 h-8 w-8 text-steel hover:text-ink"
          >
            <PanelLeftOpen className="h-4 w-4" />
            <span className="sr-only">Open sidebar</span>
          </Button>
        )}

        {children}
      </div>

      {rightPane}
    </section>
  );
}
