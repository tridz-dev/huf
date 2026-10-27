import { useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { labels } from '../labels';
import { OptionCard } from './NameAndPurposeStep';
import type { WizardApi } from './useWizardState';

const SUGGESTION: Record<string, string> = {
  keywords: 'keywords that match this purpose. Edit them below.',
  catchall: 'answer everything on this number that no other rule catches.',
  allowlist: 'answer everything, but only from allow-listed staff numbers.',
  none: 'no inbound entry points. This purpose only sends messages.',
};

export function EntryPointsStep({ wiz }: { wiz: WizardApi }) {
  const { state, intent, summaries, actions } = wiz;
  const [kwInput, setKwInput] = useState('');
  const others = (summaries[state.gateway]?.solutions ?? []).filter((s) => s.status === 'Live').length;
  const name = state.name.trim() || `this ${labels.solutionLower}`;

  const band = intent ? (
    <div className="flex items-center gap-2 rounded-md border border-line bg-paper-deep p-3 text-sm">
      <Sparkles className="h-4 w-4 shrink-0" />
      <span>
        Suggested for {intent.name}: {SUGGESTION[intent.entry] ?? ''}
      </span>
    </div>
  ) : null;

  if (intent?.entry === 'none' && !state.inbound) {
    return (
      <div className="space-y-4">
        {band}
        <p className="text-sm text-steel" data-testid="none-inbound-note">
          Nobody can start a chat with this {labels.solutionLower}. Customers who reply to an update are routed by the
          number's other rules.
        </p>
        <Button type="button" variant="outline" onClick={actions.addEntryPointsAnyway}>
          Add entry points anyway
        </Button>
      </div>
    );
  }

  const addKeyword = () => {
    actions.addKeyword(kwInput);
    setKwInput('');
  };

  return (
    <div className="space-y-5">
      {band}
      <p className="text-sm text-steel">
        {others
          ? `Another ${labels.solutionLower} already answers on this number, so customers need a way to reach this one.`
          : `This is the first on this number, so it can answer everything.`}
      </p>

      <div className="space-y-1.5">
        <label htmlFor="wizard-kw" className="text-sm font-medium">
          Keywords (message contains)
        </label>
        <div className="flex flex-wrap gap-2">
          {state.keywords.length === 0 && <span className="text-sm text-steel">None. This falls back to the catch-all.</span>}
          {state.keywords.map((k) => (
            <span key={k} className="inline-flex items-center gap-1 rounded-sm bg-paper-deep px-2 py-0.5 font-mono text-xs">
              {k}
              <button type="button" aria-label={`Remove ${k}`} onClick={() => actions.removeKeyword(k)}>
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            id="wizard-kw"
            value={kwInput}
            placeholder="Add a word"
            onChange={(e) => setKwInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addKeyword();
              }
            }}
          />
          <Button type="button" variant="outline" onClick={addKeyword}>
            Add
          </Button>
        </div>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="wizard-ref" className="text-sm font-medium">
          Ad or link tag
        </label>
        <Input id="wizard-ref" value={state.ref} onChange={(e) => actions.setRef(e.target.value)} />
        <p className="text-xs text-steel">From a click-to-WhatsApp ad or a wa.me link with this tag.</p>
      </div>

      <OptionCard on={state.triage} onClick={actions.toggleTriage}>
        <div className="text-sm font-medium">Let an assistant decide</div>
        <div className="text-xs text-steel">Asks "Reply 1 for orders, 2 for help" when nothing matches.</div>
      </OptionCard>

      <div>
        <div className="mb-1.5 text-xs uppercase tracking-wide text-steel">What the customer sees</div>
        <div className="max-w-sm rounded-lg bg-paper-deep p-3 text-sm" data-testid="customer-preview">
          {state.keywords.length ? (
            <>
              Reply with a word like <b>{state.keywords[0]}</b> to reach {name}.
            </>
          ) : (
            <>Messages that no other rule catches reach {name}.</>
          )}
        </div>
      </div>
    </div>
  );
}
