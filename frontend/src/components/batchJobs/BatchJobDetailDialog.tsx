import type { ReactNode } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { BatchJobDoc } from '@/types/batchJob.types';
import { getBatchJobStatusVariant } from '@/utils/status';
import { formatTimeAgo } from '@/utils/time';

/** One label/value row in the batch job detail dialog. */
function DetailRow({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex h-[26px] items-center justify-between gap-4">
      <span className="text-[13px] text-steel shrink-0">{label}</span>
      <span className={cn('text-[13px] truncate text-right text-ink', mono && 'font-mono')}>{value}</span>
    </div>
  );
}

/**
 * Best-effort rendering of `result_summary` as a handful of key stats.
 * `result_summary` is a free-form JSON field on the Batch Job doctype --
 * this never tries to render it generically. If it's a flat object of
 * primitive values, each key becomes a row; anything else (nested objects,
 * arrays, non-JSON strings) falls back to a plain "completed" state so the
 * dialog never shows raw, unreadable JSON to the user.
 */
function ResultSummarySection({ resultSummary }: { resultSummary: BatchJobDoc['result_summary'] }) {
  let parsed: Record<string, unknown> | null = null;

  if (resultSummary && typeof resultSummary === 'object' && !Array.isArray(resultSummary)) {
    parsed = resultSummary as Record<string, unknown>;
  } else if (typeof resultSummary === 'string' && resultSummary.trim()) {
    try {
      const asJson = JSON.parse(resultSummary);
      if (asJson && typeof asJson === 'object' && !Array.isArray(asJson)) {
        parsed = asJson as Record<string, unknown>;
      }
    } catch {
      parsed = null;
    }
  }

  const flatEntries = parsed
    ? Object.entries(parsed).filter(([, value]) => value === null || typeof value !== 'object')
    : [];

  if (flatEntries.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-line bg-paper-deep/20 p-3 text-center text-[13px] text-steel-soft">
        This batch finished successfully. No further breakdown is available.
      </div>
    );
  }

  return (
    <div className="divide-y divide-line rounded-md border border-line">
      {flatEntries.map(([key, value]) => (
        <div key={key} className="flex items-center justify-between gap-4 px-3 py-2">
          <span className="text-[13px] text-steel">{key.replace(/_/g, ' ')}</span>
          <span className="font-mono text-[13px] text-ink">{String(value ?? '—')}</span>
        </div>
      ))}
    </div>
  );
}

interface BatchJobDetailDialogProps {
  job: BatchJobDoc | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Lightweight status-view dialog for a single Batch Job -- the async-job
 * analog of AgentRunDetailPage, but scaled down to a modal since a batch
 * job's shape (status + a handful of fields) doesn't warrant its own route.
 */
export function BatchJobDetailDialog({ job, open, onOpenChange }: BatchJobDetailDialogProps) {
  if (!job) return null;

  const status = job.status || 'Pending';
  const isCompleted = status.toLowerCase() === 'completed';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle>Batch job</DialogTitle>
            <Badge variant={getBatchJobStatusVariant(status)}>{status}</Badge>
          </div>
          <DialogDescription>{job.agent || 'Unknown agent'}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="divide-y divide-line rounded-md border border-line px-3">
            <DetailRow label="Agent" value={job.agent || 'Unknown'} />
            <DetailRow label="Provider" value={job.provider || 'Not set'} />
            <DetailRow label="Requests in this batch" value={job.request_count ?? 'Not available'} />
            <DetailRow
              label="Submitted"
              value={job.submitted_at ? formatTimeAgo(job.submitted_at) : 'Not yet submitted'}
            />
            <DetailRow
              label="Completed"
              value={job.completed_at ? formatTimeAgo(job.completed_at) : 'Not yet'}
            />
            <DetailRow
              label="Estimated cost"
              value={
                typeof job.estimated_cost === 'number' ? `$${job.estimated_cost.toFixed(4)}` : 'Not available'
              }
            />
          </div>

          {job.error_message && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-[13px] text-destructive">
              {job.error_message}
            </div>
          )}

          {isCompleted && (
            <div className="space-y-2">
              <h3 className="text-[13px] font-[590] text-ink">Results</h3>
              <ResultSummarySection resultSummary={job.result_summary} />
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
