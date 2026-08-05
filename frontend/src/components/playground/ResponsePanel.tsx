import { Play } from 'lucide-react';
import { StatusDot } from '@/components/dashboard';
import { cn } from '@/lib/utils';
import type { DiffSegment } from './wordDiff';
import type { SlotState } from './types';

interface ResponsePanelProps {
  title: string;
  state: SlotState;
  /** Word-diff segments for this side (compare view, diff toggle on). */
  diffSegments?: DiffSegment[] | null;
  /** Ghost per-column run action in the footer (compare view). */
  runLabel?: string;
  onRun?: () => void;
  className?: string;
}

function formatLatency(latencyMs: number): string {
  return `${(latencyMs / 1000).toFixed(2)}s`;
}

function formatCost(cost: number): string {
  return `$${cost >= 1 ? cost.toFixed(2) : cost.toFixed(4)}`;
}

function StatusReadout({ state }: { state: SlotState }) {
  const { running, evaluating, result, evaluation } = state;

  if (running) {
    return (
      <span className="flex items-center gap-1.5 font-mono text-[11.5px] text-steel">
        <StatusDot variant="run" />
        running
      </span>
    );
  }

  if (!result) return null;

  const segments: string[] = [result.success ? 'ok' : 'held'];
  if (result.latencyMs !== undefined) segments.push(formatLatency(result.latencyMs));
  const tokens = (result.inputTokens ?? 0) + (result.outputTokens ?? 0);
  if (tokens > 0) segments.push(`${tokens} tok`);
  if (result.cost !== undefined && result.cost !== null) segments.push(formatCost(result.cost));

  return (
    <span className="flex min-w-0 items-center gap-1.5 font-mono text-[11.5px]">
      <StatusDot variant={result.success ? 'ok' : 'fail'} />
      <span className={result.success ? 'text-steel' : 'text-signal-ink'}>
        {segments.join(' · ')}
      </span>
      {evaluating && <span className="text-steel-soft">· evaluating…</span>}
      {!evaluating && evaluation && (
        <span
          className="flex min-w-0 items-center gap-1.5 text-steel"
          title={evaluation.reasoning}
        >
          <StatusDot variant={evaluation.passed ? 'ok' : 'fail'} />
          <span className="truncate">
            {evaluation.passed ? 'pass' : 'fail'} · {evaluation.reasoning}
          </span>
        </span>
      )}
    </span>
  );
}

function ResponseBody({ state, diffSegments }: { state: SlotState; diffSegments?: DiffSegment[] | null }) {
  const { running, result } = state;

  if (running && !result) {
    return <p className="px-3.5 py-3 text-[13.5px] text-steel-soft">Running…</p>;
  }

  if (!result) {
    return (
      <p className="px-3.5 py-3 text-[13.5px] text-steel-soft">
        Run a prompt to see the response here.
      </p>
    );
  }

  if (!result.success) {
    // Raw error payload in mono — this is a debugging surface, not a toast.
    const payload = result.error || 'Run failed';
    return (
      <pre className="whitespace-pre-wrap break-words px-3.5 py-3 font-mono text-[12px] leading-relaxed text-signal-ink">
        {payload}
      </pre>
    );
  }

  if (diffSegments) {
    return (
      <p className="whitespace-pre-wrap break-words px-3.5 py-3 text-[13.5px] leading-relaxed">
        {diffSegments.map((segment, index) =>
          segment.changed ? (
            <span key={index} className="bg-destructive-tint">
              {segment.text}
            </span>
          ) : (
            <span key={index}>{segment.text}</span>
          ),
        )}
      </p>
    );
  }

  return (
    <p className="whitespace-pre-wrap break-words px-3.5 py-3 text-[13.5px] leading-relaxed">
      {result.response}
    </p>
  );
}

export function ResponsePanel({
  title,
  state,
  diffSegments,
  runLabel,
  onRun,
  className,
}: ResponsePanelProps) {
  return (
    <div className={cn('flex min-h-[260px] flex-col rounded border border-line bg-panel', className)}>
      <div className="flex items-center justify-between gap-3 border-b border-line px-3.5 py-2.5">
        <span className="flex-none font-sans text-eyebrow font-medium uppercase text-steel">{title}</span>
        <StatusReadout state={state} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <ResponseBody state={state} diffSegments={diffSegments} />
      </div>

      {runLabel && onRun && (
        <div className="border-t border-line px-3.5 py-2">
          <button
            type="button"
            onClick={onRun}
            disabled={state.running}
            className="flex items-center gap-1.5 text-[12px] text-steel transition-colors hover:text-ink disabled:opacity-40"
          >
            <Play className="h-3 w-3" strokeWidth={1.8} />
            {runLabel}
          </button>
        </div>
      )}
    </div>
  );
}
