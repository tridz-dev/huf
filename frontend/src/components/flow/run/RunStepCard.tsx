import { useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, Clock, Square, XCircle } from 'lucide-react';
import { RunError } from './RunError';
import { HumanValue } from '@/components/common/HumanValue';
import { RunStepOutput } from '@/components/flow/RunStepOutput';
import { redactSecrets } from '@/lib/flow/flowToolSummary';
import type { StoryStep } from '@/lib/flow-run/story/runSteps';
import { cn } from '@/lib/utils';

export interface RunStepCardProps {
  step: StoryStep;
  names: Record<string, string>;
  titleOf: (id: string) => string | null;
  toolIdOf: (id: string) => string | undefined;
  /** The person may edit the flow: shows "Fix this step" and "Connect ...". Others get "Open this step". */
  canManage: boolean;
  onOpenStep: (id: string) => void;
  /** Loop body steps sit inside their loop's card. */
  nested?: boolean;
}

const ICONS = {
  done: <CheckCircle2 className="h-4 w-4 text-good" aria-hidden />,
  failed: <XCircle className="h-4 w-4 text-destructive" aria-hidden />,
  waiting: <Clock className="h-4 w-4 text-warning" aria-hidden />,
  stopped: <Square className="h-4 w-4 text-steel" aria-hidden />,
} as const;

const STATUS_WORD = { done: 'Done', failed: 'Failed', waiting: 'Waiting', stopped: 'Stopped' } as const;

function Iterations({ step }: { step: StoryStep }) {
  const [open, setOpen] = useState(false);
  const it = step.iterations;
  if (!it) return null;
  const label = `${it.count} ${it.count === 1 ? 'iteration' : 'iterations'}`;
  return (
    <div className="mt-2" data-testid={`flow-run-iterations-${step.id}`}>
      <button
        type="button"
        className="inline-flex min-h-6 items-center gap-1 rounded text-sm font-medium text-ink hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        data-testid={`flow-run-iterations-toggle-${step.id}`}
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" aria-hidden /> : <ChevronRight className="h-3.5 w-3.5" aria-hidden />}
        {label}
      </button>
      {open && (
        <ol className="mt-2 space-y-1.5 border-l border-line pl-3" data-testid={`flow-run-iterations-list-${step.id}`}>
          {it.results.map((r, i) => (
            <li key={i} className="text-sm" data-testid={`flow-run-iteration-${step.id}-${i + 1}`}>
              <span className="mr-2 text-xs text-steel">Round {i + 1}</span>
              <HumanValue value={redactSecrets(r)} testId={`flow-run-iteration-value-${step.id}-${i + 1}`} className="inline-block align-top" />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function RunStepCard({ step, names, titleOf, toolIdOf, canManage, onOpenStep, nested }: RunStepCardProps) {
  const failed = step.status === 'failed';
  const showName = step.title && step.title !== step.phrase;
  const output = step.hideOutput ? undefined : step.output;
  return (
    <li
      data-testid={`flow-run-step-${step.id}`}
      data-step-status={step.status === 'done' ? 'done' : step.status}
      className={cn('rounded-lg border bg-panel p-3', failed && 'border-destructive/40', step.status === 'waiting' && 'border-warning/50', nested && 'bg-paper')}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0" title={STATUS_WORD[step.status]}>{ICONS[step.status]}<span className="sr-only">{STATUS_WORD[step.status]}</span></span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium leading-snug text-ink" data-testid={`flow-run-step-phrase-${step.id}`}>{step.phrase}</div>
          {showName && <div className="text-xs text-steel" data-testid={`flow-run-step-title-${step.id}`}>{step.title}</div>}
        </div>
      </div>
      <div className="ml-6">
        {step.sentence && !failed && (
          <p className="mt-1 text-sm text-ink" data-testid={`flow-run-decision-${step.id}`}>
            {step.sentence}
            {step.comment ? <span className="text-steel">: "{step.comment}"</span> : null}
          </p>
        )}
        {step.facts?.map((f) => (
          <p key={f.label} className="mt-0.5 text-sm text-steel"><span className="text-xs">{f.label}: </span>{f.value}</p>
        ))}
        {failed && step.reason && <RunError reason={step.reason} stepId={step.id} canManage={canManage} onOpenStep={onOpenStep} />}
        {step.status === 'stopped' && step.reason && <p className="mt-1 text-sm text-steel" data-testid={`flow-run-stopped-${step.id}`}>{step.reason}</p>}
        {step.iterations && <Iterations step={step} />}
        {step.children && step.children.length > 0 && (
          <div className="mt-2">
            {step.iterations && step.iterations.count > 1 && <p className="mb-1 text-xs text-steel">Each round did the steps below. Their data is from the last round.</p>}
            <ol className="space-y-2" data-testid={`flow-run-children-${step.id}`}>
              {step.children.map((c) => (
                <RunStepCard key={c.id} step={c} names={names} titleOf={titleOf} toolIdOf={toolIdOf} canManage={canManage} onOpenStep={onOpenStep} nested />
              ))}
            </ol>
          </div>
        )}
        {!step.iterations && (
          <RunStepOutput
            stepId={step.id}
            output={output}
            rawOutput={step.hideOutput ? step.output : undefined}
            failed={failed}
            reasonShown={!!step.reason}
            decisionShown={!!step.sentence}
            names={names}
            titleOf={titleOf}
            toolId={toolIdOf(step.id)}
            dataReceived={step.receivedData}
          />
        )}
        {step.footnote && <p className="mt-1 text-xs text-steel">{step.footnote}</p>}
      </div>
    </li>
  );
}
