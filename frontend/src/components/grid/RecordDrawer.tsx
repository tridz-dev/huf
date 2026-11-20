/**
 * RecordDrawer (DESIGN.md §6.11.7): one record in a right sheet, for long
 * values and many fields. Header: title + "4 of 1,284" + previous / next
 * (also Alt+↑ / Alt+↓). Body: fields; optional history below. The grid stays
 * the place to scan; the drawer is the place to read and edit one record.
 */
import type { KeyboardEvent, ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';

export interface RecordDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  subtitle?: ReactNode;
  position?: { index: number; total: number };
  onPrev?: () => void;
  onNext?: () => void;
  children: ReactNode;
  /** History / activity section under the fields. */
  history?: ReactNode;
  footer?: ReactNode;
}

export function RecordDrawer({ open, onOpenChange, title, subtitle, position, onPrev, onNext, children, history, footer }: RecordDrawerProps) {
  const onKey = (e: KeyboardEvent) => {
    if (!e.altKey) return;
    if (e.key === 'ArrowUp' && onPrev) { e.preventDefault(); onPrev(); }
    if (e.key === 'ArrowDown' && onNext) { e.preventDefault(); onNext(); }
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" onKeyDown={onKey} className="flex w-full flex-col gap-0 p-0 sm:max-w-lg">
        <SheetHeader className="flex-row items-start gap-3 space-y-0 border-b border-line px-6 py-4 pr-12">
          <div className="min-w-0 flex-1">
            <SheetTitle className="truncate">{title}</SheetTitle>
            <SheetDescription className={subtitle ? undefined : 'sr-only'}>{subtitle ?? 'Record details'}</SheetDescription>
          </div>
          {position && (
            <div className="flex items-center gap-1">
              <span className="font-mono text-meta text-steel">{position.index.toLocaleString()} of {position.total.toLocaleString()}</span>
              <Button size="icon-sm" variant="ghost" onClick={onPrev} disabled={!onPrev} aria-label="Previous record" aria-keyshortcuts="Alt+ArrowUp">
                <ChevronUp aria-hidden="true" className="h-4 w-4" />
              </Button>
              <Button size="icon-sm" variant="ghost" onClick={onNext} disabled={!onNext} aria-label="Next record" aria-keyshortcuts="Alt+ArrowDown">
                <ChevronDown aria-hidden="true" className="h-4 w-4" />
              </Button>
            </div>
          )}
        </SheetHeader>
        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          {children}
          {history && (
            <section aria-label="History" className="space-y-2 border-t border-line pt-4">
              <h3 className="text-micro font-semibold text-steel">History</h3>
              {history}
            </section>
          )}
        </div>
        {footer && <SheetFooter className="border-t border-line px-6 py-3">{footer}</SheetFooter>}
      </SheetContent>
    </Sheet>
  );
}
