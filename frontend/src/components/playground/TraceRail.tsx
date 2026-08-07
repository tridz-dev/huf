import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { EmptyState, StatusDot } from '@/components/dashboard';
import type { StatusDotVariant } from '@/components/dashboard/ledger/LedgerSection';
import { cn } from '@/lib/utils';
import { getChildRuns, type AgentRunStep } from '@/services/agentRunApi';

interface TraceRailProps {
  /** Parent Agent Run to load the trace for. Null/undefined clears the rail. */
  agentRunId?: string | null;
  className?: string;
}

function statusVariant(status?: string | null): StatusDotVariant {
  switch (status) {
    case 'Success':
      return 'ok';
    case 'Failed':
      return 'fail';
    case 'Started':
      return 'run';
    default:
      return 'idle';
  }
}

function formatDuration(step: AgentRunStep): string {
  if (!step.start_time || !step.end_time) return '—';
  const start = new Date(step.start_time).getTime();
  const end = new Date(step.end_time).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '—';
  const ms = end - start;
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`;
}

function formatTokens(step: AgentRunStep): string {
  const total = (step.input_tokens ?? 0) + (step.output_tokens ?? 0);
  return total > 0 ? `${total} tok` : '—';
}

function StepDetail({ step }: { step: AgentRunStep }) {
  return (
    <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 border-t border-dashed border-line px-3.5 py-2.5 font-mono text-[11.5px]">
      <dt className="text-steel-soft">Provider</dt>
      <dd className="truncate text-ink">{step.provider || '—'}</dd>
      <dt className="text-steel-soft">Model</dt>
      <dd className="truncate text-ink">{step.model || '—'}</dd>
      <dt className="text-steel-soft">Input tokens</dt>
      <dd className="text-ink">{step.input_tokens ?? '—'}</dd>
      <dt className="text-steel-soft">Output tokens</dt>
      <dd className="text-ink">{step.output_tokens ?? '—'}</dd>
      <dt className="text-steel-soft">Cost</dt>
      <dd className="text-ink">
        {step.cost !== undefined && step.cost !== null ? `$${step.cost.toFixed(4)}` : '—'}
      </dd>
      <dt className="text-steel-soft">Run kind</dt>
      <dd className="truncate text-ink">{step.run_kind || '—'}</dd>
      {step.status === 'Failed' && (
        <>
          <dt className="col-span-2 mt-1 text-steel-soft">Error</dt>
          <dd className="col-span-2 whitespace-pre-wrap break-words text-signal-ink">
            {step.error_message || step.error_code || 'Run failed'}
          </dd>
        </>
      )}
    </dl>
  );
}

export function TraceRail({ agentRunId, className }: TraceRailProps) {
  const [steps, setSteps] = useState<AgentRunStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    setSelected(null);
    if (!agentRunId) {
      setSteps([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getChildRuns(agentRunId).then((rows) => {
      if (cancelled) return;
      setSteps(rows);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [agentRunId]);

  return (
    <div className={cn('flex min-h-[260px] flex-col rounded border border-line bg-panel', className)}>
      <div className="flex items-center justify-between gap-3 border-b border-line px-3.5 py-2.5">
        <span className="font-mono text-eyebrow font-medium uppercase text-steel">Trace</span>
        {loading && <Loader2 className="h-3 w-3 animate-spin text-steel-soft" />}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!agentRunId ? (
          <p className="px-3.5 py-3 text-[13.5px] text-steel-soft">
            Run a prompt to see its trace here.
          </p>
        ) : loading ? (
          <p className="px-3.5 py-3 text-[13.5px] text-steel-soft">Loading trace…</p>
        ) : steps.length === 0 ? (
          <EmptyState
            variant="passive"
            title="No steps"
            description="This run did not spawn any child runs."
            className="p-6"
          />
        ) : (
          <ul className="font-mono text-[12px]">
            {steps.map((step) => {
              const isSelected = selected === step.name;
              return (
                <li key={step.name} className="border-b border-dashed border-line last:border-b-0">
                  <button
                    type="button"
                    onClick={() => setSelected(isSelected ? null : step.name)}
                    aria-expanded={isSelected}
                    className={cn(
                      'flex w-full items-center gap-2.5 px-3.5 py-[9px] text-left transition-colors hover:bg-paper-deep',
                      isSelected && 'bg-paper-deep',
                    )}
                  >
                    <span className="text-steel-soft">{step.sequence ?? '·'}</span>
                    <StatusDot variant={statusVariant(step.status)} />
                    <span className="min-w-0 flex-1 truncate text-ink">{step.agent || step.name}</span>
                    <span className="shrink-0 text-steel">{formatDuration(step)}</span>
                    <span className="shrink-0 truncate text-steel" title={step.model || undefined}>
                      {step.model || '—'}
                    </span>
                    <span className="shrink-0 text-steel-soft">{formatTokens(step)}</span>
                  </button>
                  {isSelected && <StepDetail step={step} />}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
