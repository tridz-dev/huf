import * as Icons from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { labels } from './labels';
import type { Intent } from '@/types/solutions';

/** Intent icon names are kebab-case lucide names ("circle-help"). */
function iconFor(name: string): LucideIcon {
  const pascal = name
    .split(/[-_\s]+/)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join('');
  const found = (Icons as unknown as Record<string, LucideIcon | undefined>)[pascal];
  return found ?? Icons.Boxes;
}

interface SolutionsEmptyStateProps {
  intents: Intent[];
  onNew: () => void;
  onPurpose: (id: string) => void;
  onExisting: () => void;
  onBlank: () => void;
}

export function SolutionsEmptyState({ intents, onNew, onPurpose, onExisting, onBlank }: SolutionsEmptyStateProps) {
  return (
    <div className="rounded-xl border border-line bg-panel p-8 shadow-xs">
      <div className="flex items-start justify-between gap-4">
        <div className="max-w-xl">
          <h2 className="text-lg font-semibold text-ink">Group what your WhatsApp numbers do</h2>
          <p className="mt-1 text-sm text-steel">
            A {labels.solutionLower} bundles the agent, flows and routing for one job. One number can run several.
          </p>
        </div>
        <Button onClick={onNew}>
          <Icons.Plus className="mr-1 h-4 w-4" />
          {labels.newSolution}
        </Button>
      </div>

      <div className="mt-6 mb-2 font-mono text-eyebrow uppercase text-steel-soft">Or start from a purpose</div>
      <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
        {intents.map((intent) => {
          const Icon = iconFor(intent.icon);
          return (
            <button
              key={intent.id}
              type="button"
              onClick={() => onPurpose(intent.id)}
              className="flex items-start gap-3 rounded-lg border border-line bg-background p-3 text-left transition-colors hover:bg-paper-deep"
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-steel" />
              <span className="flex flex-col">
                <span className="text-sm font-medium text-ink">{intent.name}</span>
                <span className="text-xs text-steel">{intent.desc}</span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-4 flex items-center gap-5 text-sm">
        <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={onExisting}>
          I already have an agent or flow
        </button>
        <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={onBlank}>
          Start blank
        </button>
      </div>
    </div>
  );
}
