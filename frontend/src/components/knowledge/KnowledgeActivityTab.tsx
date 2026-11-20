import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { listIngestions, type IngestionHeader } from '@/services/knowledgeApi';
import { formatTimeAgo } from '@/utils/time';
import { IngestionProblemsSheet } from './import/IngestionProblemsSheet';
import { ingestionOrigin, ingestionSourceLabel } from './import/ingestionOrigin';
import { ingestionStatusLabel } from './import/ingestionLabels';

function statusVariant(status: string): 'pill-success' | 'pill-info' | 'pill-warning' | 'pill-danger' | 'pill-neutral' {
  if (status === 'Completed') return 'pill-success';
  if (status === 'Completed with Errors') return 'pill-warning';
  if (status === 'Failed') return 'pill-danger';
  if (status === 'Cancelled') return 'pill-neutral';
  return 'pill-info';
}

/** Recent imports for a source, newest first. */
export function KnowledgeActivityTab({ knowledgeSource, refreshKey }: { knowledgeSource: string; refreshKey?: number }) {
  const [rows, setRows] = useState<IngestionHeader[] | null>(null);
  const [error, setError] = useState(false);
  const [details, setDetails] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listIngestions(knowledgeSource, 20)
      .then((r) => alive && (setRows(r), setError(false)))
      .catch(() => alive && setError(true));
    return () => {
      alive = false;
    };
  }, [knowledgeSource, refreshKey]);

  if (error) return <p className="py-8 text-center text-sm text-destructive">We could not load recent activity. Try again.</p>;
  if (!rows) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-steel-soft" />
      </div>
    );
  }
  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-steel">Nothing has been imported yet.</p>;
  }

  return (
    <ol className="space-y-2" data-testid="activity-timeline">
      {rows.map((row) => (
        <li key={row.name} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-medium">{formatTimeAgo(row.started_at || row.modified)}</p>
            <p className="text-xs text-steel">
              {row.total_items.toLocaleString()} {row.total_items === 1 ? 'item' : 'items'}
              {row.submitted_by ? ` · added by ${row.submitted_by}` : ''}
            </p>
            <p className="truncate text-xs text-steel" data-testid="activity-source">
              Source: {ingestionSourceLabel(row.source_kind)}
              {ingestionOrigin(row) ? ` · ${ingestionOrigin(row)}` : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={statusVariant(row.status)}>{ingestionStatusLabel(row.status)}</Badge>
            <Button type="button" variant="outline" size="sm" onClick={() => setDetails(row.name)}>
              Details
            </Button>
          </div>
        </li>
      ))}
      <IngestionProblemsSheet ingestion={details} onOpenChange={(o) => !o && setDetails(null)} />
    </ol>
  );
}
