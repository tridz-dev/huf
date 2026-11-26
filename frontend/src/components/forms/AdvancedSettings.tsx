import { useEffect, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

interface AdvancedSettingsProps {
  children: ReactNode;
  /** Label of the toggle. */
  title?: string;
  /** Opens (and keeps open) the section when a hidden field has an error. */
  hasError?: boolean;
  defaultOpen?: boolean;
  className?: string;
}

/**
 * Collapsed-by-default section for rarely changed fields. It opens itself when
 * `hasError` turns true so a validation error is never hidden from the user.
 */
export function AdvancedSettings({
  children,
  title = 'Advanced settings',
  hasError = false,
  defaultOpen = false,
  className,
}: AdvancedSettingsProps) {
  const [open, setOpen] = useState(defaultOpen || hasError);

  useEffect(() => {
    if (hasError) setOpen(true);
  }, [hasError]);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className={cn('rounded-lg border', className)}>
      <CollapsibleTrigger
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium"
      >
        {title}
        <ChevronDown className={cn('h-4 w-4 transition-transform', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-4 pb-4 pt-1">{children}</CollapsibleContent>
    </Collapsible>
  );
}
