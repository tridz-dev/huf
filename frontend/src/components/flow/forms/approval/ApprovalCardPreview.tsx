import { Button } from '../../../ui/button';

export interface PreviewFact {
  label: string;
  value: string;
}

/**
 * What the approver will see, as it looks in the approvals bell and on the run page: a headline, the question, a few
 * facts and the two answers. A picture of the card (the buttons do nothing here); the words come from the examples
 * the step has, so it reads like the real thing.
 */
export function ApprovalCardPreview({ title, note, facts }: { title: string; note: string; facts: PreviewFact[] }) {
  return (
    <section className="rounded-lg border border-warning/40 bg-warning-tint/50 p-4" aria-label="Preview of the approval request" data-testid="flow-approval-preview">
      <p className="text-meta font-medium uppercase tracking-wide text-steel">Your decision is needed</p>
      <p className="mt-1 break-words text-base font-medium leading-snug text-ink" data-testid="flow-approval-preview-title">{title}</p>
      {note ? <p className="mt-1 whitespace-pre-line break-words text-sm text-ink" data-testid="flow-approval-preview-note">{note}</p> : null}
      {facts.length > 0 ? (
        <dl className="mt-3 grid grid-cols-[minmax(0,max-content)_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm" data-testid="flow-approval-preview-facts">
          {facts.map((fact, i) => (
            <div key={i} className="contents" data-testid={`flow-approval-preview-fact-${i}`}>
              <dt className="pt-0.5 text-xs text-steel">{fact.label}</dt>
              <dd className="break-words">{fact.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <div className="mt-3 flex gap-2" aria-hidden>
        <Button type="button" size="sm" variant="outline" tabIndex={-1} className="pointer-events-none">Approve</Button>
        <Button type="button" size="sm" variant="outline" tabIndex={-1} className="pointer-events-none">Reject</Button>
      </div>
    </section>
  );
}
