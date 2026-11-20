/**
 * TemplateChips (DESIGN.md §6.12.5): optional one-click starting points or
 * suggested prompts. Picking one fills the form; it never submits. A visible
 * `lead` ("Or start from an example:") frames them as shortcuts, not the full
 * menu. Each chip may carry a `description` and `meta` (what it sets up),
 * exposed as the native tooltip and to screen readers. `onMore` adds a
 * trailing "More examples…" chip that opens a TemplateGallery.
 */
import { useId, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface TemplateChip {
  id: string;
  label: string;
  icon?: ReactNode;
  /** One sentence: what it does. */
  description?: string;
  /** What it sets up, e.g. ["knowledge", "Orders table", "escalation"]. */
  meta?: string[];
}

const chipCls = 'inline-flex h-control-sm items-center gap-1.5 rounded-full border px-3 text-micro transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

export const templatePreview = (t: Pick<TemplateChip, 'description' | 'meta'>) =>
  [t.description, t.meta?.length ? `Sets up: ${t.meta.join(' · ')}` : ''].filter(Boolean).join('\n');

export function TemplateChips({ items, onPick, label = 'Start from a template', lead, activeId, onMore, moreLabel = 'More examples…', className }: {
  items: TemplateChip[];
  onPick: (id: string) => void;
  label?: string;
  /** Quiet visible text before the chips, e.g. "Or start from an example:". */
  lead?: string;
  activeId?: string;
  onMore?: () => void;
  moreLabel?: string;
  className?: string;
}) {
  const leadId = useId();
  return (
    <div role="group" aria-label={lead ? undefined : label} aria-labelledby={lead ? leadId : undefined}
      className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {lead && <span id={leadId} className="mr-1 text-micro text-steel">{lead}</span>}
      {items.map((t) => {
        const preview = templatePreview(t);
        return (
          <button key={t.id} type="button" onClick={() => onPick(t.id)} title={preview || undefined}
            aria-description={preview || undefined}
            aria-pressed={activeId ? activeId === t.id : undefined}
            className={cn(chipCls, activeId === t.id ? 'border-signal bg-signal/5 text-ink' : 'border-line bg-panel text-steel hover:bg-paper-deep hover:text-ink')}>
            {t.icon && <span aria-hidden="true">{t.icon}</span>}
            {t.label}
          </button>
        );
      })}
      {onMore && (
        <button type="button" onClick={onMore} aria-haspopup="dialog"
          className={cn(chipCls, 'border-dashed border-line bg-transparent text-steel hover:bg-paper-deep hover:text-ink')}>
          {moreLabel}
        </button>
      )}
    </div>
  );
}
