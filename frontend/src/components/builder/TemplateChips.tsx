/**
 * TemplateChips (DESIGN.md §6.12.5): one-click starting points ("Customer
 * support", "Sales follow-up") or suggested prompts. Picking one fills the
 * form; it never submits. Also used for empty-state suggestions in TryPanel.
 */
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface TemplateChip {
  id: string;
  label: string;
  icon?: ReactNode;
}

export function TemplateChips({ items, onPick, label = 'Start from a template', activeId, className }: {
  items: TemplateChip[];
  onPick: (id: string) => void;
  label?: string;
  activeId?: string;
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn('flex flex-wrap gap-1.5', className)}>
      {items.map((t) => (
        <button key={t.id} type="button" onClick={() => onPick(t.id)} aria-pressed={activeId ? activeId === t.id : undefined}
          className={cn('inline-flex h-control-sm items-center gap-1.5 rounded-full border px-3 text-micro transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            activeId === t.id ? 'border-signal bg-signal/5 text-ink' : 'border-line bg-panel text-steel hover:bg-paper-deep hover:text-ink')}>
          {t.icon && <span aria-hidden="true">{t.icon}</span>}
          {t.label}
        </button>
      ))}
    </div>
  );
}
