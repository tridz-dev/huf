import { Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { HumanValue } from '@/components/common/HumanValue';
import { JsonArea } from '@/components/common/JsonArea';
import { RunDecisionBar } from '@/components/flow/decision/RunDecisionBar';
import { describeJsonProblem } from '@/lib/flow-run/jsonErrors';
import { titleNodeIds } from '@/lib/flow-run/flowRunFormat';
import { humanizeMessageText } from '@/lib/flow-run/humanize';
import { friendlyClock, formatDuration, sinceMs } from '@/lib/flow-run/story/time';
import type { FlowRunDetail } from '@/services/flowApi';

interface RunWaitingCardProps {
  run: FlowRunDetail;
  names: Record<string, string>;
  titleOf: (id: string) => string | null;
  busy: boolean;
  /** The decision bar is shown by the phone sheet itself (stuck to the bottom) when true. */
  phone: boolean;
  onDecide: (decision: 'approved' | 'rejected') => void;
  resumePayload: string;
  onResumePayload: (value: string) => void;
  onResume: () => void;
}

/** The wait without the keys that only name its kind and step (shown to nobody; the raw view keeps them). */
const withoutInternalKeys = (waiting: Record<string, unknown>) => Object.fromEntries(Object.entries(waiting).filter(([key]) => key !== 'type' && key !== 'node_id'));

/** What the run is waiting for, with the facts and the buttons to answer it, above the steps. */
export function RunWaitingCard({ run, names, titleOf, busy, phone, onDecide, resumePayload, onResumePayload, onResume }: RunWaitingCardProps) {
  const waiting = run.waiting ?? {};
  if (!run.status?.startsWith('Waiting') || Object.keys(waiting).length === 0) return null;
  const since = run.modified_at ?? run.started_at;
  const sinceLine = since ? `Waiting since ${friendlyClock(since)} (${formatDuration(sinceMs(since))})` : '';

  if (waiting.type === 'code') {
    return (
      <section className="rounded-lg border border-warning/40 bg-warning-tint/50 p-4" data-testid="flow-run-waiting">
        <h3 className="text-sm font-semibold text-ink">Waiting for code review</h3>
        <p className="mt-1 text-sm text-ink" data-testid="run-waiting-code-note">
          {waiting.approval ? 'An administrator has to approve this code run before it continues. Check the approvals bell.' : 'The code is running in a safe space. This page updates when it is done.'}
        </p>
      </section>
    );
  }

  if (waiting.type === 'approval') {
    const message = ((waiting.instructions || waiting.message) as string | undefined) ?? '';
    const facts = Array.isArray(waiting.facts) ? (waiting.facts as Array<{ label?: unknown; value?: unknown }>).filter((f) => f.label && f.value !== undefined && f.value !== null && String(f.value) !== '') : [];
    const summary = (waiting.context_summary as string | undefined) ?? '';
    const canDecide = run.can_decide !== false;
    return (
      <section className="rounded-lg border border-warning/40 bg-warning-tint/50 p-4" data-testid="flow-run-waiting">
        <h3 className="text-sm font-semibold text-ink" data-testid="flow-run-waiting-heading">{canDecide ? 'Your decision is needed' : 'Waiting for the approvers'}</h3>
        {typeof waiting.headline === 'string' && waiting.headline && <p className="mt-1 text-base font-medium text-ink">{String(waiting.headline).replace(/^Approval needed:\s*/i, '')}</p>}
        {message && <p className="mt-1 text-sm text-ink" data-testid="flow-run-approval-message">{humanizeMessageText(message, { names })}</p>}
        {facts.length > 0 ? (
          <dl className="mt-3 grid grid-cols-[minmax(0,max-content)_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm" data-testid="flow-run-approval-facts">
            {facts.map((f) => (
              <div key={String(f.label)} className="contents">
                <dt className="text-xs text-steel pt-0.5">{String(f.label)}</dt>
                <dd className="break-words">{String(f.value)}</dd>
              </div>
            ))}
          </dl>
        ) : summary ? (
          <p className="mt-2 rounded bg-background/80 p-2 text-sm text-steel">{humanizeMessageText(summary, { names })}</p>
        ) : null}
        {sinceLine && <p className="mt-3 text-xs text-steel" data-testid="flow-run-waiting-since">{sinceLine}</p>}
        {!phone && <RunDecisionBar canDecide={canDecide} reason={run.cannot_decide_reason} busy={busy} onDecide={onDecide} />}
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-warning/40 bg-warning-tint/50 p-4" data-testid="flow-run-waiting-user">
      <h3 className="text-sm font-semibold text-ink">Waiting for your reply</h3>
      {/* The kind of wait ("user_input") and the step's id are internal words: the rows show only what the person needs; the raw data keeps all of it. */}
      <HumanValue value={titleNodeIds(withoutInternalKeys(waiting), titleOf)} rawValue={titleNodeIds(waiting, titleOf)} names={names} testId="flow-run-human-waiting" raw rawTitle="Raw data of this wait" emptyText="This run is waiting for someone to continue it." className="mt-2" />
      <div className="mt-3 space-y-2">
        <JsonArea
          surfaceKey="run-resume"
          title="Extra information to continue with (JSON, optional)"
          help={'Leave this empty to continue as it is. To pass something on to the next steps, write it as JSON, for example { "user_input": "yes" }. If the text is not valid JSON, Continue stays off until it is fixed.'}
          value={resumePayload}
          onChange={onResumePayload}
          placeholder='{ "user_input": "yes" }'
        />
        <div className="flex justify-end">
          <Button size="sm" onClick={onResume} disabled={busy || (resumePayload.trim() !== '' && !!describeJsonProblem(resumePayload))} data-testid="flow-run-resume" className="gap-2">
            <Play className="h-4 w-4" /> Continue
          </Button>
        </div>
      </div>
    </section>
  );
}
