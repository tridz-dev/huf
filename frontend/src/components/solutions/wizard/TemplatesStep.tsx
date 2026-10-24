import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { labels } from '../labels';
import { OptionCard } from './NameAndPurposeStep';
import { draftTemplateName } from './wizardModel';
import type { WizardApi } from './useWizardState';

export function TemplatesStep({ wiz }: { wiz: WizardApi }) {
  const { state, intent, templates, templatesLoading, templatesError, summaries, actions } = wiz;
  const suggested = intent?.suggested_templates ?? [];
  const approved = templates
    .filter((t) => (t.status ?? '').toLowerCase() === 'approved')
    .sort((a, b) => Number(suggested.includes(b.template_name)) - Number(suggested.includes(a.template_name)));
  const number = summaries[state.gateway]?.label || state.gateway;
  const settingsLink = `/whatsapp?gateway=${encodeURIComponent(state.gateway)}&tab=settings`;

  return (
    <div className="space-y-3">
      <p className="text-sm text-steel">
        Reuse approved templates from this account, or draft one.
        {intent ? ` Suggested ones for ${intent.name} are first.` : ''} Shared templates stay linked: edits affect every{' '}
        {labels.solutionLower} using them.
      </p>
      {templatesLoading && <p className="text-sm text-steel">Loading templates...</p>}
      {templatesError && <p className="text-sm text-destructive">{templatesError}</p>}
      {!templatesLoading && !templatesError && approved.length === 0 && (
        <p className="text-sm text-steel">No approved templates on this account yet.</p>
      )}
      {approved.map((t) => {
        const using = state.templates.includes(t.template_name);
        return (
          <OptionCard
            key={t.name}
            on={using}
            onClick={() => actions.toggleTemplate(t.template_name)}
            trailing={<Badge variant={using ? 'pill-success' : 'pill-neutral'}>{using ? 'Using' : 'Add'}</Badge>}
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm">{t.template_name}</span>
              {suggested.includes(t.template_name) && <Badge variant="pill-neutral">Suggested</Badge>}
              {t.shared && <Badge variant="pill-warning">Shared</Badge>}
            </div>
            {t.template && <div className="text-xs text-steel">{t.template}</div>}
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span className="text-[10.5px] uppercase tracking-wide text-steel">Used by</span>
              {(t.used_by ?? []).length === 0 ? (
                <span className="text-xs text-steel">Not used yet</span>
              ) : (
                (t.used_by ?? []).map((u) => (
                  <Badge key={u.solution} variant="pill-neutral">
                    {u.title || u.solution}
                  </Badge>
                ))
              )}
            </div>
          </OptionCard>
        );
      })}

      <OptionCard
        on={state.draftTemplate}
        onClick={actions.toggleDraftTemplate}
        trailing={<Badge variant={state.draftTemplate ? 'pill-warning' : 'pill-neutral'}>{state.draftTemplate ? 'Draft' : 'Add'}</Badge>}
      >
        <div className="text-sm font-medium">
          Draft a new template: <span className="font-mono font-normal">{draftTemplateName(state.name)}</span>
        </div>
        <div className="text-xs text-steel">
          {state.draftTemplate ? 'Saved as a Draft and submitted to Meta for review. Usually minutes.' : 'Starts a draft you finish later.'}
        </div>
      </OptionCard>

      {intent && (
        <div className="rounded-md border border-line p-4">
          <h3 className="text-sm font-medium">We suggest these settings for {intent.name}</h3>
          <p className="mb-2 mt-1 text-xs text-steel">Policy lives on the number. Nothing changes until you accept.</p>
          <ul className="mb-3 list-disc pl-5 text-sm">
            {intent.policy.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
          <Link to={settingsLink} className="text-sm underline">
            Review on {number}
          </Link>
        </div>
      )}
    </div>
  );
}
