import type { ReactNode } from 'react';
import { SidebarTrigger } from '@/components/ui/sidebar';
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
      <header className="flex items-center justify-between border-b border-line bg-panel px-5 py-3.5">
        <div className="flex items-center gap-3.5">
          <SidebarTrigger className="-ml-1 text-steel hover:bg-transparent hover:text-ink" />
          {title && <h1 className="font-display text-title uppercase leading-none">{title}</h1>}
        </div>
        {actions && <div className="flex items-center gap-2.5">{actions}</div>}
      </header>

      {tabs && (
        <Tabs value={tabs.value} onValueChange={tabs.onValueChange}>
          <TabsList className="bg-paper px-5">
            {tabs.items.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value} className="mr-6 px-1 py-3">
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      )}

      <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
