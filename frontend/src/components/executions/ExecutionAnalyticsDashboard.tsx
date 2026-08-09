import { useEffect, useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { EmptyStat, GaugeRow, MetricGauge } from '@/components/dashboard';
import { getExecutionAnalytics } from '@/services/executionAnalyticsApi';
import type { ExecutionAnalyticsResponse } from '@/types/executionAnalytics.types';

const number = new Intl.NumberFormat();

// A metric can't be computed (no denominator, no completed runs) rather than
// being a real zero — the "D / NO VALUE" empty-state shape (em dash, no
// "Unavailable" text) applies here, not the ordinary MetricGauge cell. Reuse
// EmptyStat inside the same padded cell shell MetricGauge uses so it sits
// flush in the GaugeRow grid.
function EmptyMetric({ label, caption }: { label: string; caption: string }) {
  return (
    <div className="px-[18px] py-4 min-w-0">
      <EmptyStat label={label} caption={caption} />
    </div>
  );
}

export function ExecutionAnalyticsDashboard() {
  const [data, setData] = useState<ExecutionAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { getExecutionAnalytics().then((result) => { setData(result); setLoading(false); }); }, []);
  if (loading) return <div className="text-sm text-muted-foreground">Loading scheduled execution analytics…</div>;
  if (!data) return null;
  const summary = data.summary;
  return <section className="space-y-3"><div className="flex items-center gap-2"><BarChart3 className="h-4 w-4" /><h2 className="text-lg font-semibold">Execution analytics</h2><span className="text-xs text-muted-foreground">Scheduled rollup · {data.metadata.granularity}</span></div><GaugeRow><MetricGauge label="Runs" value={number.format(summary.run_count)} info={`${summary.success_count} successful · ${summary.failed_count} failed`} />{summary.cache_ratio === null ? <EmptyMetric label="Cache ratio" caption="No completed runs in this period." /> : <MetricGauge label="Cache ratio" value={`${summary.cache_ratio.toFixed(1)}%`} info={`${number.format(summary.cached_tokens)} cached of ${number.format(summary.input_tokens)} input`} />}<MetricGauge label="LLM cost" value={`$${summary.total_cost.toFixed(4)}`} info="Aggregated completed runs" />{summary.average_duration_ms === null ? <EmptyMetric label="Average duration" caption="No completed runs in this period." /> : <MetricGauge label="Average duration" value={(summary.average_duration_ms / 1000).toFixed(1)} unit="s" info={`Success rate ${summary.success_rate?.toFixed(1) ?? '—'}%`} />}</GaugeRow><p className="text-xs text-muted-foreground">Metrics are read from scheduled aggregate buckets, not calculated from raw run rows in the browser.</p></section>;
}
