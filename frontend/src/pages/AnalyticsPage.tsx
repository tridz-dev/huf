import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, ArrowUpDown } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { EmptyStat, EmptyState, GaugeRow, MetricGauge } from '@/components/dashboard';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { formatTimeAgo } from '@/utils/time';
import { getExecutionAnalytics } from '@/services/executionAnalyticsApi';
import type {
  AnalyticsDimension,
  ExecutionAnalyticsResponse,
  ExecutionAnalyticsSummary,
} from '@/types/executionAnalytics.types';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';

const number = new Intl.NumberFormat();

const DIMENSION_OPTIONS: Array<{ value: AnalyticsDimension; label: string }> = [
  { value: 'provider', label: 'Provider' },
  { value: 'agent', label: 'Agent' },
  { value: 'model', label: 'Model' },
  { value: 'conversation', label: 'Conversation' },
  { value: 'run_kind', label: 'Run kind' },
];

const TIME_WINDOW_OPTIONS = [
  { value: '7d', label: 'Last 7d' },
  { value: '30d', label: 'Last 30d' },
  { value: '90d', label: 'Last 90d' },
] as const;

type TimeWindow = (typeof TIME_WINDOW_OPTIONS)[number]['value'];

/** Window length in days for each option. The API caps the window at 93 days, so 90d is the max offered. */
const TIME_WINDOW_DAYS: Record<TimeWindow, number> = {
  '7d': 7,
  '30d': 30,
  '90d': 90,
};

/** Short windows read from hourly rollups; longer ones from daily rollups. */
function granularityFor(window: TimeWindow): 'hour' | 'day' {
  return window === '7d' ? 'hour' : 'day';
}

/** Human labels for the `composition_totals` segment keys (`system/tools/knowledge/history/message`). */
const COMPOSITION_LABELS: Record<string, string> = {
  system: 'Instructions',
  tools: 'Tools',
  knowledge: 'Knowledge',
  history: 'Conversation history',
  message: 'Latest message',
};
const COMPOSITION_ORDER = ['system', 'tools', 'knowledge', 'history', 'message'];

interface BreakdownRow extends ExecutionAnalyticsSummary {
  dimension: string;
}

const ENTITY_DIMENSIONS: ReadonlySet<AnalyticsDimension> = new Set(['agent', 'provider', 'model']);

export default function AnalyticsPage() {
  const navigate = useNavigate();
  const [dimension, setDimension] = useState<AnalyticsDimension>('provider');
  const [window, setWindow] = useState<TimeWindow>('7d');
  const [data, setData] = useState<ExecutionAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [sorting, setSorting] = useState<SortingState>([]);

  const fromDate = useMemo(() => {
    const days = TIME_WINDOW_DAYS[window];
    return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
  }, [window]);
  const granularity = granularityFor(window);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getExecutionAnalytics({ fromDate, granularity, dimension }).then((result) => {
      if (cancelled) return;
      setData(result);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [fromDate, granularity, dimension]);

  const summary = data?.summary;
  const breakdowns = data?.breakdowns ?? [];
  const totalGroups = data?.metadata.breakdowns_total_count ?? 0;
  const shownGroups = breakdowns.length;
  const truncated = totalGroups > shownGroups;

  const dimensionLabel =
    DIMENSION_OPTIONS.find((option) => option.value === dimension)?.label ?? 'Dimension';

  const handleRowClick = (row: BreakdownRow) => {
    if (ENTITY_DIMENSIONS.has(dimension)) {
      navigate(`/analytics/${dimension}/${encodeURIComponent(row.dimension)}`);
    } else if (dimension === 'conversation') {
      navigate(`/chat/${row.dimension}?pane=analytics`);
    }
  };
  const rowsAreClickable = ENTITY_DIMENSIONS.has(dimension) || dimension === 'conversation';

  const columns = useMemo<ColumnDef<BreakdownRow>[]>(
    () => [
      {
        accessorKey: 'dimension',
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
          >
            {dimensionLabel}
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => (
          <div className="font-body text-[13px] font-medium text-ink">
            {row.getValue('dimension') || 'Unknown'}
          </div>
        ),
      },
      {
        accessorKey: 'run_count',
        header: ({ column }) => (
          <div className="flex justify-end">
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
            >
              Runs
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          </div>
        ),
        cell: ({ row }) => (
          <div className="text-right font-mono text-[12px] tabular-nums text-steel">
            {number.format(row.original.run_count)}
          </div>
        ),
      },
      {
        id: 'success_rate',
        header: () => <div className="text-right">Success rate</div>,
        cell: ({ row }) => {
          const rate = row.original.success_rate;
          return (
            <div className="text-right font-mono text-[12px] tabular-nums text-steel">
              {rate === null ? '—' : `${rate.toFixed(1)}%`}
            </div>
          );
        },
        sortingFn: (rowA, rowB) => (rowA.original.success_rate ?? -1) - (rowB.original.success_rate ?? -1),
      },
      {
        accessorKey: 'total_cost',
        header: ({ column }) => (
          <div className="flex justify-end">
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
            >
              LLM cost
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          </div>
        ),
        cell: ({ row }) => (
          <div className="text-right font-mono text-[12px] tabular-nums text-steel">
            ${row.original.total_cost.toFixed(4)}
          </div>
        ),
      },
      {
        id: 'average_duration_ms',
        header: () => <div className="text-right">Avg duration</div>,
        cell: ({ row }) => {
          const avg = row.original.average_duration_ms;
          return (
            <div className="text-right font-mono text-[12px] tabular-nums text-steel">
              {avg === null ? '—' : `${(avg / 1000).toFixed(1)}s`}
            </div>
          );
        },
        sortingFn: (rowA, rowB) =>
          (rowA.original.average_duration_ms ?? -1) - (rowB.original.average_duration_ms ?? -1),
      },
    ],
    [dimensionLabel]
  );

  const table = useReactTable({
    data: breakdowns as BreakdownRow[],
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  const compositionEntries = useMemo(() => {
    const totals = data?.composition_totals ?? {};
    const keys = new Set([...COMPOSITION_ORDER, ...Object.keys(totals)]);
    return COMPOSITION_ORDER.filter((key) => keys.has(key)).map((key) => ({
      key,
      label: COMPOSITION_LABELS[key] ?? key,
      value: totals[key] ?? null,
    }));
  }, [data]);
  const measuredTotal = compositionEntries.reduce(
    (sum, entry) => sum + (entry.value ?? 0),
    0
  );

  const freshnessLabel = data?.metadata.freshness ? `Updated ${formatTimeAgo(data.metadata.freshness)}` : undefined;

  return (
    <PageFrame
      title="Analytics"
      badge={<ExperimentalBadge />}
      meta={freshnessLabel}
      filters={
        <div className="flex items-center gap-3 w-full">
          <Select value={dimension} onValueChange={(value) => setDimension(value as AnalyticsDimension)}>
            <SelectTrigger size="sm" className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DIMENSION_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={window} onValueChange={(value) => setWindow(value as TimeWindow)}>
            <SelectTrigger size="sm" className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIME_WINDOW_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      }
    >
      <div className="flex flex-col gap-6">
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
              <div className="flex items-center justify-between px-[18px] py-3 border-b border-line">
                <h2 className="font-body text-[13px] font-medium text-ink">By {dimensionLabel.toLowerCase()}</h2>
                <span className="font-mono text-[11px] text-steel-soft">
                  {truncated ? `Top ${shownGroups} of ${totalGroups}` : `${shownGroups} of ${totalGroups}`}
                </span>
              </div>
              {breakdowns.length === 0 ? (
                <EmptyState
                  variant="passive"
                  icon={Activity}
                  title="No breakdown yet"
                  description="No runs recorded for this dimension in the selected window."
                />
              ) : (
                <Table>
                  <TableHeader>
                    {table.getHeaderGroups().map((headerGroup) => (
                      <TableRow key={headerGroup.id}>
                        {headerGroup.headers.map((header) => (
                          <TableHead key={header.id}>
                            {header.isPlaceholder
                              ? null
                              : flexRender(header.column.columnDef.header, header.getContext())}
                          </TableHead>
                        ))}
                      </TableRow>
                    ))}
                  </TableHeader>
                  <TableBody>
                    {table.getRowModel().rows.map((row) => (
                      <TableRow
                        key={row.id}
                        className={cn('h-11', rowsAreClickable && 'cursor-pointer hover:bg-paper-deep')}
                        onClick={rowsAreClickable ? () => handleRowClick(row.original) : undefined}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <TableCell key={cell.id}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>

            <div className="w-full rounded-lg border border-line bg-panel overflow-hidden">
              <div className="px-[18px] py-3 border-b border-line">
                <h2 className="font-body text-[13px] font-medium text-ink">Context composition</h2>
              </div>
              <div className="divide-y divide-line">
                {compositionEntries.map((entry) => {
                  if (entry.value === null) {
                    return (
                      <div
                        key={entry.key}
                        className="flex items-center justify-between px-[18px] py-3"
                      >
                        <span className="font-body text-[13px] text-ink">{entry.label}</span>
                        <span className="font-mono text-[12px] text-steel-soft">not measured</span>
                      </div>
                    );
                  }
                  const share = measuredTotal > 0 ? (entry.value / measuredTotal) * 100 : 0;
                  return (
                    <div
                      key={entry.key}
                      className="flex items-center justify-between px-[18px] py-3 gap-4"
                    >
                      <span className="font-body text-[13px] text-ink shrink-0">{entry.label}</span>
                      <div className="flex items-center gap-3 min-w-0 flex-1 justify-end">
                        <div className="h-1.5 w-32 rounded-full bg-paper-deep overflow-hidden shrink-0">
                          <div
                            className={cn('h-full rounded-full bg-steel')}
                            style={{ width: `${share}%` }}
                          />
                        </div>
                        <span className="font-mono text-[12px] tabular-nums text-steel w-28 text-right shrink-0">
                          {number.format(entry.value)} · {share.toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="border-t border-line px-[18px] py-2.5 font-body text-[12px] text-steel-soft">
                Shares are computed only from segments that could be measured; a segment marked
                &quot;not measured&quot; is excluded from the total rather than counted as zero.
              </p>
            </div>
          </>
        )}
      </div>
    </PageFrame>
  );
}
