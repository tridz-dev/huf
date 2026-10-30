import { friendlyRunTitle, startedByWords } from '@/lib/flow-run/humanize';
import { startedLine } from '@/lib/flow-run/story/headline';
import { runDuration } from '@/lib/flow-run/story/time';
import { formatAbsoluteTime } from '@/lib/serverTime';
import type { FlowRunSummary } from '@/services/flowApi';
import { OutcomeChip, RunStatusPill } from './RunStatusBits';

interface RunHistoryRowProps {
  run: FlowRunSummary;
  currentUser?: string | null;
  onOpen: () => void;
  /** Show the flow's name too (the Executions list mixes flows). */
  showFlow?: boolean;
}

/** One run in a list: "Run #12", its state and result, who started it and when, and a hint of what it was about. */
export function RunHistoryRow({ run, currentUser, onOpen, showFlow }: RunHistoryRowProps) {
  const who = startedByWords({ triggerType: run.trigger_type, owner: run.started_by, ownerName: run.started_by_name, currentUser });
  const took = runDuration(run.started_at, run.completed_at);
  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`flow-run-row-${run.name}`}
      data-run-status={run.status}
      className="cursor-pointer rounded-lg border p-3 transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); } }}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-sm font-medium text-ink" data-testid={`flow-run-row-title-${run.name}`}>
          {showFlow ? run.flow_name : friendlyRunTitle({ runNumber: run.run_number })}
        </span>
        <RunStatusPill status={run.status} stale={run.stale} testId={`flow-run-row-status-${run.name}`} />
        {run.outcome && <OutcomeChip outcome={run.outcome} testId={`flow-run-row-outcome-${run.name}`} />}
      </div>
      <div className="mt-1 text-xs text-steel" data-testid={`flow-run-row-started-${run.name}`} title={formatAbsoluteTime(run.started_at)}>
        {showFlow && run.run_number ? `Run #${run.run_number} · ` : ''}{startedLine(who, run.started_at)}{took && run.status === 'Success' ? ` · ${took}` : ''}
      </div>
      {run.input_hint && <div className="mt-0.5 truncate text-xs text-steel" data-testid={`flow-run-row-hint-${run.name}`} title={run.input_hint}>{run.input_hint}</div>}
    </div>
  );
}
