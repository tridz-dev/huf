import { HumanValue } from '@/components/common/HumanValue';
import { JsonArea } from '@/components/common/JsonArea';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SOURCE_LABEL, parseSampleInput, type SampleSource } from '@/lib/flow-test/testModel';
import type { StepTestPart } from '@/services/flow/stepTestApi';

const EMPTY_HELP = 'This step does not use data from an earlier step, so there is nothing to put in.';

/**
 * "Sample input": the data this step receives in the test, one labelled block per place it comes from, each with a
 * chip saying where the sample came from. "Edit sample" swaps the blocks for the same data as JSON the author can change.
 */
export function SampleInputSection({
  parts,
  editing,
  text,
  onText,
  onToggleEdit,
  onReset,
  canEdit,
}: {
  parts: StepTestPart[];
  editing: boolean;
  text: string;
  onText: (next: string) => void;
  onToggleEdit: () => void;
  onReset: () => void;
  canEdit: boolean;
}) {
  const parsed = editing ? parseSampleInput(text) : null;
  const edited = editing;
  return (
    <section aria-labelledby="step-test-input-title" data-testid="flow-step-test-input">
      <div className="mb-2 flex items-center gap-2">
        <h3 id="step-test-input-title" className="mr-auto text-sm font-medium">Sample input</h3>
        {edited && <Badge variant="pill-warning" data-testid="flow-step-test-source-edited">{SOURCE_LABEL.edited}</Badge>}
        {canEdit && (parts.length > 0 || editing) && (
          <Button type="button" variant="ghost" size="sm" onClick={onToggleEdit} aria-pressed={editing} data-testid="flow-step-test-edit">
            {editing ? 'Show as rows' : 'Edit as JSON'}
          </Button>
        )}
      </div>
      {editing ? (
        <div className="space-y-2">
          <JsonArea
            surfaceKey="step-test-sample"
            title="Sample input (JSON)"
            help="This is the data the test uses. Change a value to try another case. It is only used for this test; the flow itself does not change."
            value={text}
            onChange={onText}
            allowEmpty={false}
            textTestId="flow-step-test-sample-json"
          />
          {parsed && !parsed.ok && <p role="alert" className="text-xs text-destructive" data-testid="flow-step-test-sample-problem">{parsed.message}</p>}
          <Button type="button" variant="ghost" size="sm" onClick={onReset} data-testid="flow-step-test-reset">
            Use the original sample
          </Button>
        </div>
      ) : parts.length === 0 ? (
        <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground" data-testid="flow-step-test-no-input">{EMPTY_HELP}</p>
      ) : (
        <ul className="space-y-2">
          {parts.map((part) => (
            <li key={part.key} className="rounded-md border border-border bg-card p-3" data-testid={`flow-step-test-part-${part.key}`}>
              <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                <h4 className="mr-auto min-w-0 break-words text-xs font-medium">{part.title}</h4>
                <SourceChip source={part.source} partKey={part.key} />
              </div>
              {part.source === 'none' ? (
                <p className="text-xs text-muted-foreground" data-testid={`flow-step-test-part-empty-${part.key}`}>
                  {part.kind === 'input'
                    ? 'Nothing yet. Test the trigger, run the flow once, or edit the sample.'
                    : 'Nothing yet. Test that step and pin its output, run the flow once, or edit the sample.'}
                </p>
              ) : (
                <HumanValue value={part.value} testId={`flow-step-test-value-${part.key}`} emptyText="Empty" />
              )}
              {part.shortened && <p className="mt-1 text-meta text-muted-foreground">Long values are shortened here.</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function SourceChip({ source, partKey }: { source: SampleSource; partKey: string }) {
  return (
    <Badge variant={source === 'none' ? 'pill-neutral' : source === 'pinned' || source === 'trigger_sample' ? 'pill-info' : 'pill-neutral'} data-testid={`flow-step-test-source-${partKey}`} data-source={source}>
      {SOURCE_LABEL[source]}
    </Badge>
  );
}
