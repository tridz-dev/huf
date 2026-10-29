import { useState, useEffect } from 'react';
import { Activity, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { StatusDot, type StatusDotVariant } from '@/components/dashboard/ledger/LedgerSection';
import { useSearchParams } from 'react-router-dom';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { listFlowRunsPage, type FlowRunSummary } from '@/services/flowApi';
import { formatTimeAgo, calculateDuration } from '@/utils/time';
import { formatAbsoluteTime, useSiteTimezone } from '@/lib/serverTime';
import { flowRunStatusLabel } from '@/lib/flow-run/flowRunFormat';
import { useRunParam } from '@/hooks/flow/useRunParam';
import { FlowRunViewer } from '@/components/FlowRunViewer';
import { cn } from '@/lib/utils';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DEFAULT_RANGE, TIME_RANGE_MS, TIME_RANGE_OPTIONS } from './executionsRange';

const FLOW_RUN_STATUS_OPTIONS = [
  { label: 'All status', value: 'all' },
  { label: 'Queued', value: 'Queued' },
  { label: 'Running', value: 'Running' },
  { label: 'Waiting Approval', value: 'Waiting Approval' },
  { label: 'Waiting User', value: 'Waiting User' },
  { label: 'Waiting for code', value: 'Waiting Code' },
  { label: 'Success', value: 'Success' },
  { label: 'Failed', value: 'Failed' },
];

function getFlowRunStatusDot(status?: string): { variant: StatusDotVariant; label: string } {
  if (status === 'Success') return { variant: 'ok', label: status };
  if (status === 'Failed') return { variant: 'fail', label: status };
  if (status === 'Queued') return { variant: 'idle', label: status };
  return { variant: 'run', label: flowRunStatusLabel(status) || 'Running' };
}

/** The "Flow runs" tab: every Flow Run, newest first; a row opens the same Run details sheet as the flow canvas. */
export function ExecutionsFlowRunsTab() {
  useSiteTimezone();
  const [searchParams, setSearchParams] = useSearchParams();
  const [openRunId, setOpenRunId] = useRunParam();

  const { items, hasMore, initialLoading, loadingMore, search, setSearch, loadMore, total, filters, setFilter } =
    useInfiniteScroll<{ page?: number; limit?: number; start?: number; search?: string; status?: string; range?: string }, FlowRunSummary>({
      fetchFn: async (params) => {
        const rangeMs = TIME_RANGE_MS[params.range ?? DEFAULT_RANGE] ?? TIME_RANGE_MS[DEFAULT_RANGE];
        const response = await listFlowRunsPage({
          status: params.status,
          search: params.search,
          fromDate: rangeMs ? new Date(Date.now() - rangeMs).toISOString() : undefined,
          start: params.start,
          limit: params.limit,
        });
        const page = params.page ?? 1;
        const limit = params.limit ?? 20;
        return { data: response.items, hasMore: (params.start ?? (page - 1) * limit) + response.items.length < response.total, total: response.total };
      },
      initialParams: {},
      pageSize: 20,
      debounceMs: 300,
      autoLoad: true,
    });

  // Runs still in flight change on their own (and approvals expire elsewhere): refresh the first page quietly.
  const hasActive = items.some((r) => !['Success', 'Failed'].includes(r.status));
  const [refreshTick, setRefreshTick] = useState(0);
  useEffect(() => {
    if (!hasActive) return;
    const timer = setInterval(() => setRefreshTick((n) => n + 1), 5000);
    return () => clearInterval(timer);
  }, [hasActive]);
  const [liveRows, setLiveRows] = useState<Record<string, FlowRunSummary>>({});
  useEffect(() => {
    if (refreshTick === 0) return;
    const wanted = items.filter((r) => !['Success', 'Failed'].includes(r.status)).map((r) => r.name);
    if (wanted.length === 0) return;
    listFlowRunsPage({ limit: 50 }).then((page) => {
      setLiveRows((prev) => {
        const next = { ...prev };
        page.items.forEach((r) => {
          next[r.name] = r;
        });
        return next;
      });
    }).catch(() => undefined);
  }, [refreshTick]); // eslint-disable-line react-hooks/exhaustive-deps
  const rows = items.map((r) => liveRows[r.name] ?? r);

  useEffect(() => {
    const status = searchParams.get('status');
    const range = searchParams.get('range');
    const q = searchParams.get('q');
    if (q) setSearch(q);
    if (status && status !== 'all') setFilter('status', status);
    if (range && range !== DEFAULT_RANGE) setFilter('range', range);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateParams = (next: Record<string, string | undefined>) => {
    setSearchParams(
      (prev) => {
        const sp = new URLSearchParams(prev);
        Object.entries(next).forEach(([k, v]) => {
          if (v && v !== 'all' && !(k === 'range' && v === DEFAULT_RANGE)) sp.set(k, v);
          else sp.delete(k);
        });
        return sp;
      },
      { replace: true }
    );
  };

  const selectedRange = filters.range || DEFAULT_RANGE;
  const filtered = !!search || (filters.status && filters.status !== 'all') || selectedRange !== DEFAULT_RANGE;
  const headClass = 'font-mono text-eyebrow uppercase tracking-widest text-steel-soft';

  return (
    <PageFrame
      title="Executions"
      badge={<ExperimentalBadge />}
      filters={
        <FilterBar
          searchPlaceholder="Search flow runs by flow name or run id"
          searchValue={search}
          onSearchChange={(value) => {
            setSearch(value);
            updateParams({ q: value });
          }}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: FLOW_RUN_STATUS_OPTIONS,
              onChange: (value) => {
                setFilter('status', value);
                updateParams({ status: value });
              },
            },
            {
              label: 'Time',
              value: selectedRange,
              options: TIME_RANGE_OPTIONS,
              onChange: (value) => {
                setFilter('range', value);
                updateParams({ range: value });
              },
            },
          ]}
        />
      }
    >
      <div className="w-full rounded-lg border border-line bg-panel overflow-hidden" data-testid="flow-runs-table">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : rows.length === 0 ? (
          filtered ? (
            <EmptyState
              variant="no-results"
              icon={Activity}
              title="No flow runs found"
              filterTerm={search}
              secondaryAction={{
                label: 'Clear filters',
                onClick: () => {
                  setSearch('');
                  setFilter('status', 'all');
                  setFilter('range', DEFAULT_RANGE);
                  updateParams({ q: '', status: 'all', range: DEFAULT_RANGE });
                },
              }}
            />
          ) : (
            <EmptyState variant="passive" icon={Activity} title="No flow runs" description="No flow has run yet. Runs appear here when a flow is run or its trigger fires." />
          )
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className={headClass}>Flow</TableHead>
                <TableHead className={headClass}>Status</TableHead>
                <TableHead className={headClass}>Trigger</TableHead>
                <TableHead className={cn(headClass, 'text-right')}>Duration</TableHead>
                <TableHead className={cn(headClass, 'text-right')}>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((run) => {
                const { variant, label } = getFlowRunStatusDot(run.status);
                return (
                  <TableRow
                    key={run.name}
                    data-testid={`flow-run-exec-row-${run.name}`}
                    data-run-status={run.status}
                    className="h-11 cursor-pointer hover:bg-paper-deep"
                    onClick={() => setOpenRunId(run.name)}
                  >
                    <TableCell>
                      <div className="font-body text-ui-text text-ink">{run.flow_name}</div>
                      <div className="font-mono text-meta text-steel-soft">{run.name}</div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <StatusDot variant={variant} />
                        <span className="font-body text-ui-text font-normal text-steel">{label}</span>
                        {run.stale && <span className="font-body text-meta text-warning">Looks stuck</span>}
                      </div>
                    </TableCell>
                    <TableCell className="font-body text-ui-text font-normal text-steel">{run.trigger_type || 'Not available'}</TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums text-steel">
                      {calculateDuration(run.started_at, run.completed_at)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums text-steel" title={formatTimeAgo(run.started_at)}>
                      {formatAbsoluteTime(run.started_at)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>

      <LoadMoreButton hasMore={hasMore} loading={loadingMore} onLoadMore={loadMore} disabled={initialLoading} />

      {!hasMore && rows.length > 0 && (
        <div className="text-center py-4 text-sm text-steel">{total !== undefined ? `All ${total} flow runs` : 'No more flow runs to load'}</div>
      )}

      <FlowRunViewer runId={openRunId} onClose={() => setOpenRunId(null)} />
    </PageFrame>
  );
}
