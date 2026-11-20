/**
 * TemplateGallery (DESIGN.md §6.12.5): the searchable "More examples…" dialog
 * behind TemplateChips. Cards show label, one-line description and what the
 * example sets up (`meta`), grouped by `category`. Picking fills the form and
 * closes; it never submits. Search matches label, description, category, meta.
 */
import { useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { TemplateChip } from './TemplateChips';

export interface GalleryTemplate extends TemplateChip { category?: string }

export function TemplateGallery({ open, onOpenChange, items, onPick, activeId, title = 'Examples', description = 'Pick one to fill in the form. You can edit everything after.' }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: GalleryTemplate[];
  onPick: (id: string) => void;
  activeId?: string;
  title?: string;
  description?: string;
}) {
  const [q, setQ] = useState('');
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return items;
    return items.filter((t) => [t.label, t.description, t.category, ...(t.meta ?? [])].join(' ').toLowerCase().includes(s));
  }, [items, q]);
  const groups = useMemo(() => {
    const m = new Map<string, GalleryTemplate[]>();
    shown.forEach((t) => { const k = t.category ?? ''; m.set(k, [...(m.get(k) ?? []), t]); });
    return [...m.entries()];
  }, [shown]);

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setQ(''); }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <Input type="search" aria-label="Search examples" placeholder="Search, e.g. invoices, WhatsApp, schedule" value={q}
          onChange={(e) => setQ(e.target.value)} autoFocus />
        <div className="max-h-[60vh] overflow-y-auto pr-1" data-testid="template-gallery">
          {shown.length === 0 && <p className="py-8 text-center text-ui-text text-steel">No examples match. Describe your agent in your own words instead.</p>}
          {groups.map(([cat, list]) => (
            <section key={cat} aria-label={cat || undefined} className="mb-4 last:mb-0">
              {cat && <h3 className="mb-2 text-micro font-medium uppercase tracking-wide text-steel">{cat}</h3>}
              <ul className="grid gap-2 sm:grid-cols-2">
                {list.map((t) => (
                  <li key={t.id}>
                    <button type="button" onClick={() => { onPick(t.id); onOpenChange(false); setQ(''); }}
                      aria-pressed={activeId ? activeId === t.id : undefined}
                      className={cn('flex h-full w-full flex-col gap-1 rounded border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        activeId === t.id ? 'border-signal bg-signal/5' : 'border-line bg-panel hover:bg-paper-deep')}>
                      <span className="text-ui-text font-medium text-ink">{t.label}</span>
                      {t.description && <span className="text-micro text-steel">{t.description}</span>}
                      {!!t.meta?.length && <span className="text-micro text-steel"><span className="sr-only">Sets up: </span>{t.meta.join(' · ')}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
