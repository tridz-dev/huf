import { useMemo } from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FieldHint } from '../FieldHint';
import { Label } from '../../ui/label';
import { MoreOptions } from '../frame/MoreOptions';
import { DataInput } from '../data/DataInput';
import { OutcomeChip } from '../run/RunStatusBits';
import { fromTextRefs, toTextRefs } from '@/lib/flow-data/textRefs';
import { parseValue } from '@/lib/flow-data/chips';
import { previewOf } from '@/lib/flow-data/model';
import { useFlowContext } from '../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useDataCatalog } from '../data/useDataCatalog';
import type { EndConfig, EndOutcome, FlowNode, FlowNodeData, OutcomeTone } from '../../../types/flow.types';
import { useAsValue } from './useAsValue';
import { Section } from './formKit';

const TONES: Array<{ tone: OutcomeTone; label: string; help: string; dot: string }> = [
  { tone: 'good', label: 'Good', help: 'It went the way you wanted.', dot: 'bg-good' },
  { tone: 'neutral', label: 'Neutral', help: 'Just information.', dot: 'bg-steel' },
  { tone: 'bad', label: 'Bad', help: 'It did not go the way you wanted.', dot: 'bg-destructive' },
];

/** The End step: how the run reads when it ends here (the headline of the run), and optionally what it returns. */
export function EndForm({ node }: { node: FlowNode }) {
  const { updateNodeData, activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const { model } = useDataCatalog(node.id);
  const end: EndConfig = node.data.endConfig ?? {};
  const outcome: EndOutcome = end.outcome ?? {};
  const tone: OutcomeTone = outcome.tone ?? 'neutral';
  const save = (next: EndConfig) => updateNodeData(node.id, (data) => ({ ...data, endConfig: next }) as FlowNodeData);
  const saveOutcome = (patch: EndOutcome) => {
    const merged: EndOutcome = { ...outcome, ...patch };
    if (!merged.label) delete merged.label;
    const next: EndConfig = { ...end };
    // No wording and neutral is what an End without an outcome already is.
    if (!merged.label && (merged.tone === undefined || merged.tone === 'neutral')) delete next.outcome;
    else next.outcome = merged;
    save(next);
  };
  const [label, toLabel] = useAsValue(outcome.label ?? '', toTextRefs, (v) => fromTextRefs(v) ?? '');

  const shown = useMemo(() => previewOf(parseValue(toTextRefs(outcome.label ?? '')).segments, model).text.trim() || 'Finished', [outcome.label, model]);
  const flowName = activeFlow?.name || 'This flow';
  return (
    <Section title="End" hint="The flow finishes here. The outcome is the headline people read for the run, like Approved or Refund sent.">
      <p className="text-xs text-muted-foreground" data-testid="flow-end-lead">The flow finishes here. Say how the run ended so people can tell at a glance.</p>
      <div className="space-y-2" data-testid="flow-end-outcome">
        <DataInput
          id="end-outcome-label"
          nodeId={node.id}
          testId="flow-field-output-outcome-label"
          label="Outcome"
          optional
          placeholder="Finished"
          hint="How the run reads when it ends here, for example Approved, Rejected or Refund sent. Leave empty to show Finished. You can add details with + Use data."
          value={label}
          onChange={(v) => saveOutcome({ label: toLabel(v) })}
        />
        <div>
          <Label size="sm" id="end-tone-label">How did it go?</Label>
          <div role="radiogroup" aria-labelledby="end-tone-label" className="mt-1 flex flex-wrap gap-2" data-testid="flow-end-tone">
            {TONES.map((t) => {
              const on = t.tone === tone;
              return (
                <button
                  key={t.tone}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  disabled={!canManage}
                  title={t.help}
                  data-testid={`flow-end-tone-${t.tone}`}
                  onClick={() => saveOutcome({ tone: t.tone })}
                  className={cn(
                    'flex min-h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    on ? 'border-signal bg-signal/10 text-foreground' : 'border-border text-muted-foreground hover:text-foreground'
                  )}
                >
                  <span className={cn('h-2.5 w-2.5 rounded-full', t.dot)} aria-hidden />
                  {t.label}
                  {on && <Check className="h-3 w-3" aria-hidden />}
                </button>
              );
            })}
          </div>
          <FieldHint testId="flow-hint-end-tone">{TONES.find((t) => t.tone === tone)?.help} The colour shows in the run list.</FieldHint>
        </div>
        <div className="rounded-lg border border-border p-3" aria-label="Preview of the run headline" data-testid="flow-end-preview">
          <p className="text-meta font-medium uppercase tracking-wide text-steel">How the run will read</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <OutcomeChip outcome={{ label: shown, tone }} testId="flow-end-preview-chip" />
          </div>
          <p className="mt-2 break-words text-lg font-semibold leading-snug text-ink" data-testid="flow-end-preview-headline">{shown}</p>
          <p className="mt-0.5 text-sm text-steel">Run finished · {flowName}</p>
        </div>
      </div>
      <MoreOptions defaultOpen={end.value !== undefined && end.value !== null && end.value !== ''} testId="flow-more-options-end">
        <DataInput
          id="end-value"
          nodeId={node.id}
          testId="flow-field-output-value"
          label="Result"
          optional
          hint="What the flow hands back, shown in the run details. Leave it empty if you do not need a result."
          value={end.value}
          onChange={(v) => save({ ...end, value: v })}
        />
      </MoreOptions>
    </Section>
  );
}
