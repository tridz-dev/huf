import { HumanValue } from '@/components/common/HumanValue';
import { DocFieldValue } from '@/components/flow/RunViewerParts';
import { deskDocUrl, summarizeDocPayload } from '@/lib/flow-run/flowRunDoc';
import { redactSecrets } from '@/lib/flow/flowToolSummary';
import type { RunStory } from '@/lib/flow-run/story/runSteps';

interface RunInputBlocksProps {
  story: RunStory;
  triggerEvent?: string | null;
  names: Record<string, string>;
}

/** Data the run started with that no step shows: a document that changed, or input the first step does not repeat. */
export function RunInputBlocks({ story, triggerEvent, names }: RunInputBlocksProps) {
  const { input } = story;
  const doc = summarizeDocPayload(input, triggerEvent);
  if (doc) {
    return (
      <section data-testid="flow-run-document">
        <h3 className="mb-3 text-sm font-semibold text-ink">Document</h3>
        <div className="space-y-3 rounded-lg border bg-panel p-4">
          <div className="text-sm">
            <span className="font-medium" data-testid="flow-run-document-doctype">{doc.doctype}</span>{' '}
            <a className="font-mono text-xs text-primary underline" href={deskDocUrl(doc.doctype, doc.name)} target="_blank" rel="noreferrer" data-testid="flow-run-document-name">{doc.name}</a>
            {doc.event && <span className="ml-2 rounded-full border px-2 py-0.5 text-xs text-steel" data-testid="flow-run-document-event">{doc.event}</span>}
          </div>
          {doc.fields.length > 0 && (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm" data-testid="flow-run-document-fields">
              {doc.fields.map((f) => (
                <div key={f.key} className="contents">
                  <dt className="pt-0.5 text-xs text-steel">{f.label}</dt>
                  <dd className="whitespace-pre-wrap break-words"><DocFieldValue field={f} /></dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        <HumanValue value={undefined} raw rawValue={redactSecrets(input)} testId="flow-run-full-payload" rawTitle="Everything the document contained" rawTextTestId="flow-run-input" className="mt-3" />
      </section>
    );
  }
  if (!story.separateInput) return null;
  return (
    <section data-testid="flow-run-trigger-input">
      <h3 className="mb-3 text-sm font-semibold text-ink">What this run started with</h3>
      <HumanValue value={redactSecrets(input)} names={names} testId="flow-run-human-input" raw rawTitle="Raw data this run started with" rawTextTestId="flow-run-input" />
    </section>
  );
}
