import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { Health, HealthKey, InputCounts } from './ingestionLabels';

const HEALTH_VARIANT: Record<HealthKey, 'pill-success' | 'pill-info' | 'pill-warning' | 'pill-neutral' | 'pill-danger'> = {
  ready: 'pill-success',
  updating: 'pill-info',
  attention: 'pill-warning',
  empty: 'pill-neutral',
  broken: 'pill-danger',
  paused: 'pill-neutral',
};

export function HealthBadge({ health, className }: { health: Health; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={className} data-testid="health-badge">
          <Badge variant={HEALTH_VARIANT[health.key]}>{health.label}</Badge>
        </span>
      </TooltipTrigger>
      <TooltipContent>{health.hint}</TooltipContent>
    </Tooltip>
  );
}

interface DocumentsSummaryProps {
  counts: InputCounts;
  onReviewProblems?: () => void;
  className?: string;
}

export function DocumentsSummary({ counts, onReviewProblems, className }: DocumentsSummaryProps) {
  const parts: Array<{ label: string; tone: string }> = [
    { label: `${counts.ready.toLocaleString()} ready`, tone: 'text-good' },
  ];
  if (counts.inProgress > 0) {
    parts.push({ label: `${counts.inProgress.toLocaleString()} in progress`, tone: 'text-signal-ink' });
  }
  if (counts.failed > 0) {
    parts.push({ label: `${counts.failed.toLocaleString()} need attention`, tone: 'text-destructive' });
  }
  if (counts.skipped > 0) {
    parts.push({ label: `${counts.skipped.toLocaleString()} skipped`, tone: 'text-steel' });
  }
  return (
    <div
      className={cn('flex flex-wrap items-center gap-x-4 gap-y-1 text-sm font-body', className)}
      data-testid="documents-summary"
    >
      <span className="font-medium text-ink">
        {counts.total.toLocaleString()} {counts.total === 1 ? 'document' : 'documents'}
      </span>
      {parts.map((p) => (
        <span key={p.label} className={p.tone}>
          {p.label}
        </span>
      ))}
      {counts.failed + counts.skipped > 0 && onReviewProblems && (
        <button type="button" onClick={onReviewProblems} className="text-signal-ink underline-offset-4 hover:underline">
          Review
        </button>
      )}
    </div>
  );
}
