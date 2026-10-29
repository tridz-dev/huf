import { AlertCircle, CheckCircle2, ChevronRight, PowerOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import { stripText } from './frameIssues';

/**
 * 36px strip under the panel header: "2 things to finish >" (amber; click jumps to the first one) or "Ready" (green).
 * A step that is turned off says so instead, because nothing in it runs.
 */
export function StatusStrip({ count, disabled, onJump }: { count: number; disabled?: boolean; onJump: () => void }) {
  if (count > 0) {
    return (
      <button
        type="button"
        onClick={onJump}
        data-testid="flow-status-strip"
        data-state="todo"
        className={cn(
          'flex h-9 w-full shrink-0 items-center gap-2 border-b border-border bg-warning-tint px-3.5 text-left text-xs font-medium text-warning',
          'hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring'
        )}
        aria-label={`${stripText(count)}. Go to the first one`}
      >
        <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1 truncate">{stripText(count)}</span>
        <ChevronRight className="h-4 w-4 shrink-0" aria-hidden />
      </button>
    );
  }
  if (disabled) {
    return (
      <div data-testid="flow-status-strip" data-state="off" className="flex h-9 w-full shrink-0 items-center gap-2 border-b border-border bg-muted px-3.5 text-xs font-medium text-muted-foreground">
        <PowerOff className="h-4 w-4 shrink-0" aria-hidden />
        <span className="truncate">Turned off. The flow skips this step.</span>
      </div>
    );
  }
  return (
    <div data-testid="flow-status-strip" data-state="ready" role="status" className="flex h-9 w-full shrink-0 items-center gap-2 border-b border-border px-3.5 text-xs font-medium text-good">
      <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden />
      <span>Ready</span>
    </div>
  );
}
