import { useState, useEffect } from 'react';
import { Activity, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { RunStatusPill, OutcomeChip } from '@/components/flow/run/RunStatusBits';
import { ExecutionsTabsBar } from './ExecutionsTabsBar';
import { RUN_STATUS_FILTERS, isFinishedStatus } from '@/lib/flow-run/story/runStatus';
import { friendlyRunTitle, startedByWords, triggerLabel } from '@/lib/flow-run/humanize';
import { friendlyClock, runDuration } from '@/lib/flow-run/story/time';
import { useUser } from '@/contexts/UserContext';
import { useSearchParams } from 'react-router-dom';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { listFlowRunsPage, type FlowRunSummary } from '@/services/flowApi';
import { formatTimeAgo } from '@/utils/time';
import { formatAbsoluteTime, useSiteTimezone } from '@/lib/serverTime';
import { useRunParam } from '@/hooks/flow/useRunParam';
import { FlowRunViewer } from '@/components/FlowRunViewer';
import { cn } from '@/lib/utils';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DEFAULT_RANGE, TIME_RANGE_MS, TIME_RANGE_OPTIONS } from './executionsRange';

/** The "Flow runs" tab: every Flow Run, newest first; a row opens the same Run details sheet as the flow canvas. */
export function ExecutionsFlowRunsTab() {
  useSiteTimezone();
  const { user } = useUser();
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
  const hasActive = items.some((r) => !isFinishedStatus(r.status));
  const [refreshTick, setRefreshTick] = useState(0);
  useEffect(() => {
    if (!hasActive) return;
    const timer = setInterval(() => setRefreshTick((n) => n + 1), 5000);
    return () => clearInterval(timer);
  }, [hasActive]);
  const [liveRows, setLiveRows] = useState<Record<string, FlowRunSummary>>({});
  useEffect(() => {
    if (refreshTick === 0) return;
    const wanted = items.filter((r) => !isFinishedStatus(r.status)).map((r) => r.name);
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
      tabs={<ExecutionsTabsBar active="flow-runs" />}
      filters={
        <FilterBar
          searchPlaceholder="Search by flow name"
          searchValue={search}
          onSearchChange={(value) => {
            setSearch(value);
            updateParams({ q: value });
          }}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: RUN_STATUS_FILTERS,
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
                <TableHead className={headClass}>Result</TableHead>
                <TableHead className={headClass}>Started by</TableHead>
                <TableHead className={cn(headClass, 'text-right')}>Took</TableHead>
                <TableHead className={cn(headClass, 'text-right')}>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((run) => {
                const who = startedByWords({ triggerType: run.trigger_type, owner: run.started_by, ownerName: run.started_by_name, currentUser: user?.name });
                return (
                  <TableRow
                    key={run.name}
                    data-testid={`flow-run-exec-row-${run.name}`}
                    data-run-status={run.status}
                    className="min-h-11 cursor-pointer hover:bg-paper-deep"
                    onClick={() => setOpenRunId(run.name)}
                  >
                    <TableCell>
                      <div className="font-body text-ui-text text-ink">{run.flow_name}</div>
                      <div className="font-body text-meta text-steel-soft" data-testid={`flow-run-exec-title-${run.name}`}>
                        {friendlyRunTitle({ runNumber: run.run_number })}{run.input_hint ? ` · ${run.input_hint}` : ''}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <RunStatusPill status={run.status} stale={run.stale} testId={`flow-run-exec-status-${run.name}`} />
                        {run.outcome && <OutcomeChip outcome={run.outcome} testId={`flow-run-exec-outcome-${run.name}`} />}
                      </div>
                    </TableCell>
                    <TableCell className="font-body text-ui-text font-normal text-steel">
                      <div>{who.charAt(0).toUpperCase() + who.slice(1)}</div>
                      <div className="text-meta text-steel-soft" data-testid={`flow-run-exec-trigger-${run.name}`}>{triggerLabel(run.trigger_type)}</div>
                    </TableCell>
                    <TableCell className="text-right font-body text-ui-text tabular-nums text-steel">
                      {run.status === 'Success' || run.status === 'Failed' ? runDuration(run.started_at, run.completed_at) || '-' : '-'}
                    </TableCell>
                    <TableCell className="text-right font-body text-ui-text tabular-nums text-steel" title={`${formatAbsoluteTime(run.started_at)} (${formatTimeAgo(run.started_at)})`}>
                      {friendlyClock(run.started_at)}
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
