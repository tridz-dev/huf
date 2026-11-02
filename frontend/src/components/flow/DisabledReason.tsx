import { cloneElement, isValidElement, useId } from 'react';
import type { MouseEvent, ReactElement, ReactNode } from 'react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface BlockableProps {
  disabled?: boolean;
  onClick?: (event: MouseEvent<HTMLElement>) => void;
  'aria-describedby'?: string;
}

/**
 * Wraps a control that is off for a reason and says why. The control is not `disabled` (a disabled button cannot be
 * focused, so keyboard and touch users never reached the explanation): it is `aria-disabled`, still tabbable, ignores
 * clicks, and the reason opens as a tooltip on hover and on focus.
 */
export function DisabledReason({ reason, children }: { reason: string | null; children: ReactNode }) {
  const reasonId = useId();
  if (!reason) return <>{children}</>;
  const control = isValidElement<BlockableProps>(children)
    ? cloneElement(children as ReactElement<BlockableProps>, {
        disabled: undefined,
        'aria-disabled': true,
        'aria-describedby': reasonId,
        onClick: (event: MouseEvent<HTMLElement>) => {
          event.preventDefault();
          event.stopPropagation();
        },
      } as BlockableProps & { 'aria-disabled': boolean })
    : children;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex" data-testid="disabled-reason">
            {control}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[260px]">
          {reason}
        </TooltipContent>
      </Tooltip>
      <span id={reasonId} className="sr-only">
        {reason}
      </span>
    </TooltipProvider>
  );
}
