/**
 * LinkedListPopover (DESIGN.md §6.10.12): "Used by 2 agents ▾" — a trigger
 * that opens a short list of the things linked to this resource. Each item:
 * label, optional mono meta, and either an `href` (navigates) or `onSelect`.
 * An empty state says what linking would do; an optional footer action
 * ("Manage access") ends the list. Built from ui primitives; no raw buttons.
 */
import type { ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

export interface LinkedItem {
  id: string;
  label: string;
  meta?: ReactNode;
  icon?: ReactNode;
  href?: string;
  onSelect?: () => void;
}

export interface LinkedListPopoverProps {
  /** Trigger text, e.g. "Used by 2 agents". */
  label: ReactNode;
  items: LinkedItem[];
  /** Heading inside the popover, e.g. "Agents using this". */
  title?: string;
  empty?: ReactNode;
  footer?: { label: string; onClick: () => void; icon?: ReactNode };
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

const ROW = 'h-auto w-full justify-start gap-2 px-2 py-1.5 text-left font-normal';

export function LinkedListPopover({ label, items, title, empty = 'Nothing linked yet.', footer, open, onOpenChange, className }: LinkedListPopoverProps) {
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="link" size="sm" className={cn('h-auto gap-1 px-0', className)}>
          {label}
          <ChevronDown aria-hidden="true" className="h-3 w-3" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-1.5">
        {title && <p className="px-2 pb-1 pt-1 text-micro font-semibold text-steel">{title}</p>}
        {items.length === 0 ? (
          <p data-testid="linked-empty" className="px-2 py-3 text-micro text-steel">{empty}</p>
        ) : (
          <ul aria-label={title ?? 'Linked items'} className="max-h-64 overflow-y-auto">
            {items.map((it) => {
              const body = (
                <>
                  {it.icon && <span aria-hidden="true" className="text-steel">{it.icon}</span>}
                  <span className="min-w-0 flex-1 truncate text-ui-text text-ink">{it.label}</span>
                  {it.meta && <span className="shrink-0 font-mono text-meta text-steel-soft">{it.meta}</span>}
                </>
              );
              return (
                <li key={it.id}>
                  {it.href ? (
                    <Button asChild variant="ghost" size="sm" className={ROW}><a href={it.href}>{body}</a></Button>
                  ) : it.onSelect ? (
                    <Button variant="ghost" size="sm" className={ROW} onClick={it.onSelect}>{body}</Button>
                  ) : (
                    <div className="flex items-center gap-2 px-2 py-1.5">{body}</div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {footer && (
          <>
            <Separator className="my-1" />
            <Button variant="ghost" size="sm" className={cn(ROW, 'text-signal-ink')} onClick={footer.onClick}>
              {footer.icon}
              {footer.label}
            </Button>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}
