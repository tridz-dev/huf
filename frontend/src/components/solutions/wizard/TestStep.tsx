import { TestChat } from '../TestChat';
import { labels } from '../labels';
import type { WizardApi } from './useWizardState';

export function TestStep({ wiz }: { wiz: WizardApi }) {
  const { state, gateways, summaries, draft, actions } = wiz;
  const chips = [state.keywords[0] ? `a ${state.keywords[0]} for friday` : '', 'hi', '1'].filter(Boolean);
  const testGateways = gateways.map((g) => ({
    name: g.name,
    label: summaries[g.name]?.label || g.gateway_name || g.name,
    phone: summaries[g.name]?.phone || '',
  }));
  return (
    <div className="space-y-4">
      <p className="text-sm text-steel">
        Try it before going live. The {labels.solutionLower} is included in routing for this test only. Nothing is saved yet.
      </p>
      <TestChat
        embedded
        gateways={testGateways}
        gateway={state.gateway}
        onGatewayChange={actions.setGateway}
        chips={chips}
        adChips={state.ref.trim() ? [state.ref.trim()] : []}
        draft={draft}
        solutionLabels={{ [draft.title]: draft.title }}
      />
      {!state.existing && (
        <p data-testid="no-target-note" className="rounded-md border border-line bg-paper-deep p-3 text-sm">
          No agent or flow is chosen: it will be saved as paused until you choose one.
        </p>
      )}
      <label className="flex cursor-pointer items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={state.testMode}
          onChange={(e) => actions.setTestMode(e.target.checked)}
        />
        <span>
          Keep it in test mode after saving
          <span className="block text-xs text-steel">Paused, only you can message it. Go live from its page when ready.</span>
        </span>
      </label>
    </div>
  );
}
