/**
 * Checklist (DESIGN.md §6.10.10): a short, dismissible "next steps" list
 * shown after a resource first becomes usable. Done steps are checked and
 * quiet; open steps are actions. Dismissal is the caller's to persist.
 */
import { ArrowRight, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface ChecklistItem {
  label: string;
  done?: boolean;
  onClick?: () => void;
}

export interface ChecklistProps {
  title?: string;
  items: ChecklistItem[];
  onDismiss?: () => void;
  className?: string;
}

export function Checklist({ title = 'Next steps', items, onDismiss, className }: ChecklistProps) {
  return (
    <section aria-label={title} data-testid="checklist" className={cn('rounded border border-line bg-panel px-4 py-3', className)}>
      <div className="flex items-center justify-between">
        <h3 className="text-ui-text font-semibold text-ink">{title}</h3>
        {onDismiss && (
          <Button type="button" variant="ghost" size="icon-sm" aria-label={`Dismiss ${title.toLowerCase()}`} onClick={onDismiss}>
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
      <ul className="mt-2 space-y-1.5 text-ui-text">
        {items.map((item) => (
          <li key={item.label}>
            {item.done || !item.onClick ? (
              <span className={cn('flex items-center gap-2', item.done ? 'text-steel' : 'text-ink')}>
                {item.done ? <Check aria-hidden="true" className="h-4 w-4 text-good" /> : <ArrowRight aria-hidden="true" className="h-4 w-4 text-steel-soft" />}
                {item.label}
                {item.done && <span className="sr-only"> (done)</span>}
              </span>
            ) : (
              <Button type="button" variant="link" size="sm" className="h-auto gap-2 px-0" onClick={item.onClick}>
                <ArrowRight aria-hidden="true" className="h-4 w-4" />
                {item.label}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
