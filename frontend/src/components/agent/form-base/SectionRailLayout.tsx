import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export type SectionStatus = 'empty' | 'partial' | 'complete' | 'coming_soon';

export interface RailSection {
  id: string;
  label: string;
  status?: SectionStatus;
  meta?: string;
  badge?: string;
}

interface SectionRailLayoutProps {
  sections: RailSection[];
  children: ReactNode;
  className?: string;
}

const statusClassMap: Record<SectionStatus, string> = {
  complete: 'bg-emerald-500',
  partial: 'bg-amber-400',
  empty: 'bg-border border border-border',
  coming_soon: 'bg-blue-400',
};

export function SectionRailLayout({ sections, children, className }: SectionRailLayoutProps) {
  const scrollToSection = (sectionId: string) => {
    const target = document.getElementById(`agent-section-${sectionId}`);
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className={cn('grid gap-6 lg:grid-cols-[180px_1fr]', className)}>
      <aside className="hidden lg:block lg:sticky lg:top-6 lg:self-start">
        <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Sections</p>
        <div className="space-y-1 rounded-lg border bg-card p-2">
          {sections.map((section) => {
            const status = section.status ?? 'empty';
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => scrollToSection(section.id)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted/50"
              >
                <span className={cn('h-2 w-2 shrink-0 rounded-full', statusClassMap[status])} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs text-foreground">{section.label}</span>
                  {section.meta ? <span className="block truncate text-[11px] text-muted-foreground">{section.meta}</span> : null}
                </span>
                {section.badge ? (
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                    {section.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </aside>

      <div className="space-y-4">{children}</div>
    </div>
  );
}

interface SectionBlockProps {
  id: string;
  title: string;
  description?: string;
  badge?: ReactNode;
  children: ReactNode;
}

export function SectionBlock({ id, title, description, badge, children }: SectionBlockProps) {
  return (
    <section id={`agent-section-${id}`} className="scroll-mt-6 rounded-lg border bg-card">
      <div className="border-b px-5 py-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {badge}
        </div>
        {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
      </div>
      <div className="space-y-4 p-5">{children}</div>
    </section>
  );
}
