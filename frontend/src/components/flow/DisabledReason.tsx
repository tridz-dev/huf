import type { ReactNode } from 'react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

/** Wraps a control so a disabled state can still explain itself (disabled buttons swallow hover events). */
export function DisabledReason({ reason, children }: { reason: string | null; children: ReactNode }) {
  if (!reason) return <>{children}</>;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} className="inline-flex [&>button:disabled]:pointer-events-none" data-testid="disabled-reason">
            {children}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[260px]">
          {reason}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
