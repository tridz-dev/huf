import type { ReactNode } from 'react';
import { AppTopbar } from '@/layouts/AppTopbar';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

export interface WorkSurfaceTab {
  value: string;
  label: string;
}

interface WorkSurfaceFrameProps {
  /** Optional Big Shoulders title in the compact topbar (work surfaces only — DESIGN.md §6.9). */
  title?: string;
  /** Right side of the topbar. */
  actions?: ReactNode;
  /** Optional mode tabs — shared §6.5 underline vocabulary on the paper baseline. */
  tabs?: {
    value: string;
    onValueChange: (value: string) => void;
    items: WorkSurfaceTab[];
  };
  children: ReactNode;
}

/**
 * DESIGN.md §6.9 work-surface template (Playground, Chat): full-bleed, compact
 * topbar that may carry the Big Shoulders title, optional sentence-case tabs,
 * content fills the remaining height. No page head, no max-width.
 */
export function WorkSurfaceFrame({ title, actions, tabs, children }: WorkSurfaceFrameProps) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-paper text-ink">
      <AppTopbar hideBorder={Boolean(tabs)}>
        <div className="flex flex-1 items-center justify-between gap-3">
          {title && <h1 className="font-display text-xl font-bold uppercase leading-none">{title}</h1>}
          {actions && <div className="flex items-center gap-2.5">{actions}</div>}
        </div>
      </AppTopbar>

      {tabs && (
        <div className="shrink-0 bg-paper px-4">
          <Tabs value={tabs.value} onValueChange={tabs.onValueChange} className="w-full">
            <TabsList layout="scroll" className="w-full border-b border-line bg-transparent p-0">
              {tabs.items.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value} className="shrink-0">
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      )}

      <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
