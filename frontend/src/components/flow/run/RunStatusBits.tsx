import { Badge } from '@/components/ui/badge';
import { StatusPill } from '@/components/common/StatusPill';
import { runStatusPill, type RunStatusInput } from '@/lib/flow-run/story/runStatus';
import type { RunOutcome } from '@/services/flow/flowRunStoryTypes';
import { cn } from '@/lib/utils';

/** The run's state in the one status set (Finished, Failed, Stuck...). */
export function RunStatusPill({ status, stale, className, testId = 'flow-run-status' }: RunStatusInput & { className?: string; testId?: string }) {
  const { kind, label } = runStatusPill({ status, stale });
  return <StatusPill kind={kind} label={label} className={className} data-testid={testId} />;
}

const TONE_VARIANT = { good: 'pill-success', bad: 'pill-danger', neutral: 'pill-neutral' } as const;

/** What the run came to for the business (Approved, Rejected, Timed out, or the End step's own wording). */
export function OutcomeChip({ outcome, className, testId = 'flow-run-outcome' }: { outcome: RunOutcome; className?: string; testId?: string }) {
  return (
    <Badge variant={TONE_VARIANT[outcome.tone] ?? 'pill-neutral'} className={cn('shrink-0 whitespace-nowrap px-2 py-0.5', className)} data-testid={testId} data-tone={outcome.tone}>
      {outcome.label}
    </Badge>
  );
}

/** The grey "Test" chip on a run that skipped everything that would send or change something. */
export function TestRunChip({ className, testId = 'flow-run-test-chip', label = 'Test' }: { className?: string; testId?: string; label?: string }) {
  return (
    <Badge variant="pill-neutral" className={cn('shrink-0 whitespace-nowrap px-2 py-0.5', className)} title="A test run: nothing was sent or changed" data-testid={testId}>
      {label}
    </Badge>
  );
}
