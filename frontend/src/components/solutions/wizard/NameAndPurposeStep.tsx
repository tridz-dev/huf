import * as Icons from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { labels } from '../labels';
import type { WizardApi } from './useWizardState';

function iconFor(name: string): LucideIcon {
  const pascal = name
    .split('-')
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join('');
  return (Icons as unknown as Record<string, LucideIcon | undefined>)[pascal] ?? Icons.Boxes;
}

/** Selectable card used across wizard steps. */
export function OptionCard({
  on,
  onClick,
  children,
  trailing,
  testId,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
  trailing?: ReactNode;
  testId?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      data-testid={testId}
      onClick={onClick}
      className={cn(
        'flex w-full items-start gap-3 rounded-md border p-3 text-left transition-colors',
        on ? 'border-ink bg-paper-deep' : 'border-line bg-background hover:bg-paper-deep',
      )}
    >
      <div className="min-w-0 flex-1">{children}</div>
      {trailing}
    </button>
  );
}

function qualityPill(rating: string | null | undefined) {
  if (!rating) return <Badge variant="pill-neutral">No rating</Badge>;
  const r = rating.toLowerCase();
  const variant = r.includes('high') || r === 'green' ? 'pill-success' : r.includes('medium') || r === 'yellow' ? 'pill-warning' : 'pill-danger';
  return <Badge variant={variant}>{rating} quality</Badge>;
}

const nativeSelect =
  'h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

export function NameAndPurposeStep({ wiz }: { wiz: WizardApi }) {
  const { state, intents, intent, gateways, summaries, targets, actions } = wiz;
  const placeholder = intent ? intent.sample_name : `For example: Order desk`;
  const selectedKey = state.existing ? `${state.existing.type}:${state.existing.name}` : '';

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <label htmlFor="wizard-name" className="text-sm font-medium">
          Name
        </label>
        <Input
          id="wizard-name"
          value={state.name}
          placeholder={placeholder}
          onChange={(e) => actions.setName(e.target.value)}
        />
        <p className="text-xs text-steel">Required. You can rename it any time.</p>
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium">
          {labels.purpose} <span className="font-normal text-steel">(optional)</span>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {intents.map((i) => {
            const Icon = iconFor(i.icon);
            return (
              <OptionCard key={i.id} on={state.mode === 'intent' && state.intentId === i.id} onClick={() => actions.selectIntent(i)}>
                <div className="flex items-start gap-2">
                  <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    <div className="text-sm font-medium">{i.name}</div>
                    <div className="text-xs text-steel">{i.desc}</div>
                  </div>
                </div>
              </OptionCard>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant={state.mode === 'existing' ? 'default' : 'outline'}
            onClick={() => actions.selectMode('existing')}
          >
            Use an agent or flow I already have
          </Button>
          <Button
            type="button"
            size="sm"
            variant={state.mode === 'blank' && !state.intentId ? 'default' : 'outline'}
            onClick={() => actions.selectMode('blank')}
          >
            No purpose, start blank
          </Button>
        </div>
        <p className="text-xs text-steel">
          A purpose only suggests entry points, templates and settings. It never creates an agent for you.
        </p>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="wizard-existing" className="text-sm font-medium">
          Answered by {state.mode !== 'existing' && <span className="font-normal text-steel">(optional)</span>}
        </label>
        <select
          id="wizard-existing"
          className={nativeSelect}
          value={selectedKey}
          onChange={(e) => {
            if (!e.target.value) return actions.setExisting(null);
            const [type, ...rest] = e.target.value.split(':');
            actions.setExisting({ type: type as 'Agent' | 'Flow', name: rest.join(':') });
          }}
        >
          {state.mode !== 'existing' && <option value="">Choose later</option>}
          {targets.length === 0 && state.mode === 'existing' && <option value="">No agents or flows yet</option>}
          {targets.map((t) => (
            <option key={`${t.type}:${t.name}`} value={`${t.type}:${t.name}`}>
              {t.label} ({t.type.toLowerCase()})
            </option>
          ))}
        </select>
        <p className="text-xs text-steel">The agent or flow that replies. Without one, the {labels.solutionLower} is saved as paused.</p>
      </div>

      <div className="space-y-2">
        <div className="text-sm font-medium">{labels.runsOn}</div>
        {gateways.length === 0 && <p className="text-sm text-steel">Add a WhatsApp gateway first to run a {labels.solutionLower} on it.</p>}
        {gateways.map((g) => {
          const sum = summaries[g.name];
          const live = (sum?.solutions ?? []).filter((s) => s.status === 'Live');
          return (
            <OptionCard
              key={g.name}
              on={state.gateway === g.name}
              onClick={() => actions.setGateway(g.name)}
              trailing={qualityPill(sum?.quality?.rating)}
              testId={`gateway-${g.name}`}
            >
              <div className="text-sm">
                <span className="font-medium">{sum?.label || g.gateway_name || g.name}</span>{' '}
                <span className="font-mono text-xs text-steel">{sum?.phone}</span>
              </div>
              <div className="text-xs text-steel">
                {live.length
                  ? `Already used by ${live.map((s) => s.title).join(', ')}. Sharing is fine.`
                  : 'Nobody uses it yet.'}
              </div>
            </OptionCard>
          );
        })}
      </div>
    </div>
  );
}
