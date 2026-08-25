import { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Activity } from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from 'recharts';
import { PageFrame } from '@/layouts/PageFrame';
import { EmptyStat, EmptyState, GaugeRow, MetricGauge } from '@/components/dashboard';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { ContextBar } from '@/components/ui/context-bar';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { formatTimeAgo } from '@/utils/time';
import { getExecutionAnalytics } from '@/services/executionAnalyticsApi';
import type {
  AnalyticsDimension,
  ExecutionAnalyticsResponse,
} from '@/types/executionAnalytics.types';

const number = new Intl.NumberFormat();

/** Same window as AnalyticsPage's default -- last 7 days, hourly buckets. */
const WINDOW_DAYS = 7;
const GRANULARITY = 'hour' as const;

const DIMENSION_LABELS: Record<string, string> = {
  provider: 'Provider',
  agent: 'Agent',
  model: 'Model',
  conversation: 'Conversation',
  run_kind: 'Run kind',
};

const chartConfig = {
  runCount: {
    label: 'Runs',
    color: 'var(--ink)',
  },
} satisfies ChartConfig;

/**
 * One lightweight trend chart over `series[].run_count`, bucketed by hour.
 * Deliberately not a reuse of ContextGrowthChart -- that component is shaped
 * for per-turn conversation series (a `sequence` x-axis, nullable points);
 * this is a time-bucketed rollup series with a real timestamp axis.
 */
function EntityTrendChart({ series }: { series: ExecutionAnalyticsResponse['series'] }) {
  const data = useMemo(
    () =>
      [...series]
        .sort((a, b) => a.bucket_start.localeCompare(b.bucket_start))
        .map((point) => ({
          bucketStart: point.bucket_start,
          runCount: point.run_count,
        })),
    [series]
  );

  if (data.length === 0) {
    return (
      <div className="flex h-[180px] items-center justify-center rounded-lg border border-line bg-panel">
        <p className="text-[12px] text-steel-soft">No runs to chart in this window.</p>
      </div>
    );
  }

  return (
    <ChartContainer config={chartConfig} className="aspect-auto h-[220px] w-full">
      <AreaChart data={data} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--line)" />
        <XAxis
          dataKey="bucketStart"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          tickFormatter={(value: string) =>
            new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric' })
          }
          minTickGap={32}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          width={36}
          allowDecimals={false}
        />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={(label) => new Date(label as string).toLocaleString()}
            />
          }
        />
        <Area
          dataKey="runCount"
          type="monotone"
          stroke="var(--color-runCount)"
          fill="var(--color-runCount)"
          fillOpacity={0.12}
          strokeWidth={1.75}
          isAnimationActive={false}
        />
      </AreaChart>
    </ChartContainer>
  );
}

export default function AnalyticsEntityDetailPage() {
  const { dimension, entity } = useParams<{ dimension: string; entity: string }>();
  const [data, setData] = useState<ExecutionAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fromDate = useMemo(
    () => new Date(Date.now() - WINDOW_DAYS * 24 * 60 * 60 * 1000).toISOString(),
    []
  );

  useEffect(() => {
    if (!dimension || !entity) return;
    let cancelled = false;
    setLoading(true);
    getExecutionAnalytics({
      fromDate,
      granularity: GRANULARITY,
      dimension: dimension as AnalyticsDimension,
      // `entity` from useParams() is already percent-decoded by React
      // Router's route matching -- decoding it again corrupts any value
      // containing a raw "%" (and throws a URIError for malformed ones).
      entity,
    }).then((result) => {
      if (cancelled) return;
      setData(result);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [fromDate, dimension, entity]);

  const summary = data?.summary;
  const series = data?.series ?? [];
  const dimensionLabel = (dimension && DIMENSION_LABELS[dimension]) || 'Dimension';
  const entityLabel = entity ?? '';
  const freshnessLabel = data?.metadata.freshness ? `Updated ${formatTimeAgo(data.metadata.freshness)}` : undefined;

  return (
    <PageFrame
      title={
        <span className="flex items-center gap-2">
          <Link
            to="/executions?tab=analytics"
            className="flex items-center gap-1 text-steel-soft hover:text-ink transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <span>{entityLabel || 'Entity'}</span>
        </span>
      }
      badge={<ExperimentalBadge />}
      meta={freshnessLabel}
    >
      <div className="flex flex-col gap-6">
        <div className="font-body text-[12px] text-steel-soft -mt-2">
          <Link to="/executions?tab=analytics" className="hover:text-ink transition-colors">
            Analytics
          </Link>
          <span className="mx-1.5">/</span>
          <span>{dimensionLabel}</span>
          <span className="mx-1.5">/</span>
          <span className="text-ink">{entityLabel || '—'}</span>
        </div>

        {loading ? (
          <div className="px-[18px] py-4 font-body text-[13px] text-steel">Loading analytics…</div>
        ) : !summary || summary.run_count === 0 ? (
          <EmptyState
            variant="passive"
            icon={Activity}
            title="No analytics yet"
            description="Analytics accrue as agent runs complete in this window."
          />
        ) : (
          <>
            <GaugeRow>
              <MetricGauge
                label="Runs"
                value={number.format(summary.run_count)}
                info={`${summary.success_count} successful · ${summary.failed_count} failed`}
              />
              {summary.cache_ratio === null ? (
                <div className="px-[18px] py-4 min-w-0">
                  <EmptyStat label="Cache ratio" caption="No completed runs in this period." />
                </div>
              ) : (
                <MetricGauge
                  label="Cache ratio"
                  value={`${summary.cache_ratio.toFixed(1)}%`}
                  info={`${number.format(summary.cached_tokens)} cached of ${number.format(summary.input_tokens)} input`}
                />
              )}
              <MetricGauge label="LLM cost" value={`$${summary.total_cost.toFixed(4)}`} info="Aggregated completed runs" />
              {summary.average_duration_ms === null ? (
                <div className="px-[18px] py-4 min-w-0">
                  <EmptyStat label="Average duration" caption="No completed runs in this period." />
                </div>
              ) : (
                <MetricGauge
                  label="Average duration"
                  value={(summary.average_duration_ms / 1000).toFixed(1)}
                  unit="s"
                  info={`Success rate ${summary.success_rate?.toFixed(1) ?? '—'}%`}
                />
              )}
            </GaugeRow>

            <div className="w-full rounded-lg border border-line bg-panel overflow-hidden">
              <div className="px-[18px] py-3 border-b border-line">
                <h2 className="font-body text-[13px] font-medium text-ink">Runs over time</h2>
              </div>
              <div className="p-[18px]">
                <EntityTrendChart series={series} />
              </div>
            </div>

            {data?.composition_totals && Object.keys(data.composition_totals).length > 0 && (
              <div className="w-full rounded-lg border border-line bg-panel overflow-hidden">
                <div className="px-[18px] py-3 border-b border-line">
                  <h2 className="font-body text-[13px] font-medium text-ink">Context composition</h2>
                </div>
                <div className="p-[18px]">
                  <ContextBar
                    segments={data.composition_totals as any}
                    total={null}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </PageFrame>
  );
}
