import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useSocketStatus, type SocketStatus } from '@/contexts/SocketContext';
import { cn } from '@/lib/utils';

const COPY: Record<SocketStatus, { label: string; detail: string; dot: string }> = {
  connected: { label: 'Live updates on', detail: 'Changes appear here as they happen.', dot: 'bg-good' },
  connecting: { label: 'Connecting...', detail: 'Setting up live updates.', dot: 'bg-steel animate-pulse' },
  offline: {
    label: 'Live updates off',
    detail: 'Some screens may need a refresh to show new results. Reload the page to retry.',
    dot: 'bg-signal',
  },
};

/** One small status dot for the live-updates connection; replaces the old repeating error toast. */
export function ConnectionIndicator() {
  const status = useSocketStatus();
  const copy = COPY[status];
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            role="status"
            tabIndex={0}
            aria-label={copy.label}
            data-testid="connection-indicator"
            data-status={status}
            className="flex h-6 w-4 items-center justify-center"
          >
            <span className={cn('h-2 w-2 rounded-full', copy.dot)} />
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[240px]">
          <p className="font-medium">{copy.label}</p>
          <p className="opacity-80">{copy.detail}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
