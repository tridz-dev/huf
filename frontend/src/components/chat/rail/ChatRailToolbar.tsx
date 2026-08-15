import { PanelLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

// Spec section 28 toolbar rule: Panel glyph, bar on the left. 40px height (h-chat-header)
// positioned at the top-left of the shell. Search control is deliberately absent until
// conversation search exists — a control that promises a function it does not have is
// worse than its absence.
export interface ChatRailToolbarProps {
  onToggleRail: () => void;
  className?: string;
}

export function ChatRailToolbar({ onToggleRail, className }: ChatRailToolbarProps) {
  return (
    <div className={cn('flex h-chat-header flex-none items-center gap-2.5 px-3', className)}>
      <button
        type="button"
        onClick={onToggleRail}
        className="flex h-6 w-6 items-center justify-center rounded-chat-row text-steel transition-colors hover:bg-chat-row-hover hover:text-ink"
      >
        <PanelLeft className="h-4 w-4" />
        <span className="sr-only">Collapse conversation rail</span>
      </button>
    </div>
  );
}
