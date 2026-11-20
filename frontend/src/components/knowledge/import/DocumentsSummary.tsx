import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { DocFilter } from './docFilter';
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
  filter?: DocFilter | null;
  onFilterChange?: (filter: DocFilter | null) => void;
  className?: string;
}

export function DocumentsSummary({ counts, filter = null, onFilterChange, className }: DocumentsSummaryProps) {
  const parts: Array<{ label: string; tone: string; key?: DocFilter }> = [
    { label: `${counts.ready.toLocaleString()} ready`, tone: 'text-good', key: 'ready' },
  ];
  if (counts.inProgress > 0) {
    parts.push({ label: `${counts.inProgress.toLocaleString()} in progress`, tone: 'text-signal-ink' });
  }
  if (counts.failed > 0) {
    parts.push({ label: `${counts.failed.toLocaleString()} need attention`, tone: 'text-destructive', key: 'attention' });
  }
  if (counts.skipped > 0) {
    parts.push({ label: `${counts.skipped.toLocaleString()} skipped`, tone: 'text-steel', key: 'skipped' });
  }
  return (
    <div
      className={cn('flex flex-wrap items-center gap-x-4 gap-y-1 text-sm font-body', className)}
      data-testid="documents-summary"
    >
      <span className="font-medium text-ink">
        {counts.total.toLocaleString()} {counts.total === 1 ? 'document' : 'documents'}
      </span>
      {parts.map((p) =>
        p.key && onFilterChange ? (
          <button
            key={p.label}
            type="button"
            aria-pressed={filter === p.key}
            title={filter === p.key ? 'Show all documents' : 'Show only these'}
            onClick={() => onFilterChange(filter === p.key ? null : p.key!)}
            className={cn(p.tone, 'rounded px-1 underline-offset-4 hover:underline', filter === p.key && 'bg-muted font-medium underline')}
          >
            {p.label}
          </button>
        ) : (
          <span key={p.label} className={p.tone}>
            {p.label}
          </span>
        ),
      )}
    </div>
  );
}
