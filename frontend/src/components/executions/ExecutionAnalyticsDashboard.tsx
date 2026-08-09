import { useEffect, useState } from 'react';
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

export interface ExecutionAnalyticsDashboardProps {
  /** ISO start of the analytics window. Omit for the API's own default (last 7 days). */
  fromDate?: string;
  /** Rollup granularity to query — hour for short windows, day for longer ones. */
  granularity?: 'hour' | 'day';
}

/**
 * The 4-column metric strip (Runs / Cache ratio / LLM cost / Avg duration).
 *
 * Deliberately has no border, heading, or icon of its own — it nests
 * directly inside the single bordered card the Executions page also uses
 * for its filter row and data grid, so a second "Execution analytics"
 * label here would just be redundant chrome.
 */
export function ExecutionAnalyticsDashboard({ fromDate, granularity }: ExecutionAnalyticsDashboardProps) {
  const [data, setData] = useState<ExecutionAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getExecutionAnalytics({ fromDate, granularity }).then((result) => {
      if (cancelled) return;
      setData(result);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [fromDate, granularity]);

  if (loading) {
    return <div className="px-[18px] py-4 font-body text-[13px] text-steel">Loading scheduled execution analytics…</div>;
  }
  if (!data) return null;

  const summary = data.summary;

  return (
    <div>
      <GaugeRow className="rounded-none border-0">
        <MetricGauge
          label="Runs"
          value={number.format(summary.run_count)}
          info={`${summary.success_count} successful · ${summary.failed_count} failed`}
        />
        {summary.cache_ratio === null ? (
          <EmptyMetric label="Cache ratio" caption="No completed runs in this period." />
        ) : (
          <MetricGauge
            label="Cache ratio"
            value={`${summary.cache_ratio.toFixed(1)}%`}
            info={`${number.format(summary.cached_tokens)} cached of ${number.format(summary.input_tokens)} input`}
          />
        )}
        <MetricGauge label="LLM cost" value={`$${summary.total_cost.toFixed(4)}`} info="Aggregated completed runs" />
        {summary.average_duration_ms === null ? (
          <EmptyMetric label="Average duration" caption="No completed runs in this period." />
        ) : (
          <MetricGauge
            label="Average duration"
            value={(summary.average_duration_ms / 1000).toFixed(1)}
            unit="s"
            info={`Success rate ${summary.success_rate?.toFixed(1) ?? '—'}%`}
          />
        )}
      </GaugeRow>
      <p className="border-t border-line px-[18px] py-2.5 font-body text-[12px] text-steel-soft">
        Metrics are read from scheduled aggregate buckets, not calculated from raw run rows in the browser.
      </p>
    </div>
  );
}
