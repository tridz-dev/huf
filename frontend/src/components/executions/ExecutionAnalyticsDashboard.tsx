import { useEffect, useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyStat } from '@/components/dashboard';
import { getExecutionAnalytics } from '@/services/executionAnalyticsApi';
import type { ExecutionAnalyticsResponse } from '@/types/executionAnalytics.types';

const number = new Intl.NumberFormat();

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{value}</div><p className="mt-1 text-xs text-muted-foreground">{detail}</p></CardContent></Card>;
}

// A metric can't be computed (no denominator, no completed runs) rather than
// being a real zero — the "D / NO VALUE" empty-state shape (em dash, no
// "Unavailable" text) applies here, not the ordinary Metric tile.
function EmptyMetric({ label, caption }: { label: string; caption: string }) {
  return (
    <Card>
      <div className="p-6">
        <EmptyStat label={label} caption={caption} />
      </div>
    </Card>
  );
}

export function ExecutionAnalyticsDashboard() {
  const [data, setData] = useState<ExecutionAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { getExecutionAnalytics().then((result) => { setData(result); setLoading(false); }); }, []);
  if (loading) return <div className="text-sm text-muted-foreground">Loading scheduled execution analytics…</div>;
  if (!data) return null;
  const summary = data.summary;
  return <section className="space-y-3"><div className="flex items-center gap-2"><BarChart3 className="h-4 w-4" /><h2 className="text-lg font-semibold">Execution analytics</h2><span className="text-xs text-muted-foreground">Scheduled rollup · {data.metadata.granularity}</span></div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><Metric label="Runs" value={number.format(summary.run_count)} detail={`${summary.success_count} successful · ${summary.failed_count} failed`} />{summary.cache_ratio === null ? <EmptyMetric label="Cache ratio" caption="No completed runs in this period." /> : <Metric label="Cache ratio" value={`${summary.cache_ratio.toFixed(1)}%`} detail={`${number.format(summary.cached_tokens)} cached of ${number.format(summary.input_tokens)} input`} />}<Metric label="LLM cost" value={`$${summary.total_cost.toFixed(4)}`} detail="Aggregated completed runs" />{summary.average_duration_ms === null ? <EmptyMetric label="Average duration" caption="No completed runs in this period." /> : <Metric label="Average duration" value={`${(summary.average_duration_ms / 1000).toFixed(1)}s`} detail={`Success rate ${summary.success_rate?.toFixed(1) ?? '—'}%`} />}</div><p className="text-xs text-muted-foreground">Metrics are read from scheduled aggregate buckets, not calculated from raw run rows in the browser.</p></section>;
}
