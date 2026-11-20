/**
 * SettingsSheet (DESIGN.md §6.10.9): the settings of one resource, in a
 * right-side sheet over the page instead of a Settings tab. Order is fixed:
 * everyday sections, then a collapsed "Advanced", then the danger zone last.
 */
import { useState, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { cn } from '@/lib/utils';

export interface SettingsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  description?: string;
  children: ReactNode;
  /** Save / Cancel row. Omit when every control saves on change. */
  footer?: ReactNode;
}

export function SettingsSheet({ open, onOpenChange, title = 'Settings', description, children, footer }: SettingsSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b border-line px-6 py-4">
          <SheetTitle>{title}</SheetTitle>
          {description ? <SheetDescription>{description}</SheetDescription> : <SheetDescription className="sr-only">{title}</SheetDescription>}
        </SheetHeader>
        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <SheetFooter className="border-t border-line px-6 py-3">{footer}</SheetFooter>}
      </SheetContent>
    </Sheet>
  );
}

/** A titled group of fields. Title optional for the first, obvious group. */
export function SettingsSection({ title, children, className }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn('space-y-4', className)} aria-label={title}>
      {title && <h3 className="text-micro font-semibold text-steel">{title}</h3>}
      {children}
    </section>
  );
}

/** Collapsed-by-default group for settings most people never change. */
export function SettingsAdvanced({ children, label = 'Advanced', defaultOpen = false }: { children: ReactNode; label?: string; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="-ml-2 gap-1 text-steel">
          <ChevronRight aria-hidden="true" className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-90')} />
          {label}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-4 pt-3">{children}</CollapsibleContent>
    </Collapsible>
  );
}

export interface DangerZoneProps {
  title: string;
  /** Consequence in plain words, with numbers: "Removes all 1,241 documents. This can't be undone." */
  description: string;
  actionLabel: string;
  /** Open a confirm dialog here; never delete directly from this click. */
  onAction: () => void;
}

export function DangerZone({ title, description, actionLabel, onAction }: DangerZoneProps) {
  return (
    <section aria-label="Danger zone" className="flex items-start gap-4 rounded border border-destructive/30 p-4">
      <div className="min-w-0 flex-1">
        <p className="text-ui-text font-semibold text-destructive">{title}</p>
        <p className="mt-0.5 text-micro text-steel">{description}</p>
      </div>
      <Button type="button" variant="destructive-ghost" size="sm" onClick={onAction}>
        {actionLabel}
      </Button>
    </section>
  );
}
