import { useState, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../../ui/collapsible';
import { cn } from '@/lib/utils';

/**
 * Optional settings of a step, folded away so the required ones stay in view. Opens by itself when `defaultOpen`
 * (an optional setting already has a value) and when a field inside is asked to be focused.
 */
export function MoreOptions({
  children,
  label = 'More options',
  defaultOpen = false,
  testId = 'flow-more-options',
}: {
  children: ReactNode;
  label?: string;
  defaultOpen?: boolean;
  testId?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen} data-more-options data-testid={testId} data-state={open ? 'open' : 'closed'}>
      <CollapsibleTrigger
        type="button"
        className="flex min-h-8 w-full items-center gap-1 rounded-md py-1 text-left text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        data-testid={`${testId}-toggle`}
      >
        <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-90')} aria-hidden />
        {label}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-4">{children}</CollapsibleContent>
    </Collapsible>
  );
}
