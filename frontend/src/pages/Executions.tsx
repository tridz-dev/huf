import { useState, useEffect, useMemo } from 'react';
import { Activity, ArrowUpDown, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { StatusDot, type StatusDotVariant } from '@/components/dashboard/ledger/LedgerSection';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getAgentRuns, type AgentRunDoc } from '@/services/agentRunApi';
import { getFlowStepLabels, listFlowRunsPage, type FlowRunSummary } from '@/services/flowApi';
import { formatTimeAgo, calculateDuration } from '@/utils/time';
import { formatAbsoluteTime, toServerDatetime, useSiteTimezone } from '@/lib/serverTime';
import { useRunParam } from '@/hooks/useRunParam';
import { FlowRunViewer } from '@/components/FlowRunViewer';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { cn } from '@/lib/utils';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ExecutionAnalyticsDashboard } from '@/components/executions/ExecutionAnalyticsDashboard';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import AnalyticsPage from '@/pages/AnalyticsPage';

const DEFAULT_RANGE = '24h';

/** Sub-tabs hosted on this page — kept in the URL so a link like
 * `/executions?tab=analytics` opens directly on the Analytics tab. */
const EXECUTIONS_TABS = ['runs', 'flow-runs', 'analytics'] as const;
type ExecutionsTab = (typeof EXECUTIONS_TABS)[number];
const DEFAULT_TAB: ExecutionsTab = 'runs';

const TIME_RANGE_OPTIONS = [
  { label: 'Last 24h', value: '24h' },
  { label: 'Last 7d', value: '7d' },
  { label: 'Last 30d', value: '30d' },
  { label: 'All time', value: 'all' },
];

/** Window length in ms for each range option; `null` means unbounded ("All time"). */
const TIME_RANGE_MS: Record<string, number | null> = {
  '24h': 24 * 60 * 60 * 1000,
  '7d': 7 * 24 * 60 * 60 * 1000,
  '30d': 30 * 24 * 60 * 60 * 1000,
  all: null,
};

/** Columns whose values are numeric/temporal and read better right-aligned with tabular figures. */
const RIGHT_ALIGNED_COLUMNS = new Set(['cost', 'cached_tokens', 'duration', 'started']);

function getRunStatusDot(status?: string): { variant: StatusDotVariant; label: string } {
  const normalized = status?.toLowerCase() || '';
  if (normalized === 'success') return { variant: 'ok', label: status || 'Success' };
  if (normalized === 'failed') return { variant: 'fail', label: status || 'Failed' };
  if (normalized === 'queued') return { variant: 'idle', label: status || 'Queued' };
  return { variant: 'run', label: status || 'Started' };
}

/** The "Runs" tab — this is the original Executions page body, unchanged. */
function ExecutionsRunsTab() {
  useSiteTimezone();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [agents, setAgents] = useState<Array<{ name: string }>>([]);

  const {
    items: runs,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    filters,
    setFilter,
  } = useInfiniteScroll<
    {
      page?: number;
      limit?: number;
      start?: number;
      search?: string;
      status?: string;
      agents?: string;
      range?: string;
    },
    AgentRunDoc
  >({
    fetchFn: async (params) => {
      // `range` is only present in params once a non-default value is picked
      // (setFilter drops the key when it equals the "no-op" sentinel — here
      // that's the not-yet-initialized state, so an absent range still means
      // "use the default window", same as the Status/Agent filters below).
      const rangeKey = params.range ?? DEFAULT_RANGE;
      const rangeMs = TIME_RANGE_MS[rangeKey] ?? TIME_RANGE_MS[DEFAULT_RANGE];
      const runFilters: Array<[string, string, unknown]> = [['is_child', '=', '0']];
      if (rangeMs) {
        runFilters.push(['start_time', '>=', toServerDatetime(new Date(Date.now() - rangeMs))]);
      }

      const response = await getAgentRuns({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status as 'Started' | 'Queued' | 'Success' | 'Failed' | 'all' | undefined,
        agents: params.agents ? params.agents.split(',').filter(Boolean) : undefined,
        filters: runFilters,
      });

      if (Array.isArray(response)) {
        return {
          data: response,
          hasMore: false,
          total: response.length,
        };
      }

      return {
        data: response.items,
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    initialParams: {},
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
  });

  // Runs made by a flow step (tool call, agent, router) carry no agent of their own: name them
  // "Flow: <flow name> > <step title>" so they read as part of the flow, not "Unknown Agent".
  const [flowLabels, setFlowLabels] = useState<Record<string, string>>({});
  useEffect(() => {
    const wanted = runs.filter((r) => r.flow_run && !(r.name in flowLabels));
    if (wanted.length === 0) return;
    let cancelled = false;
    getFlowStepLabels(wanted.map((r) => ({ flow_run: r.flow_run as string, flow_node_id: r.flow_node_id }))).then((labels) => {
      if (cancelled) return;
      setFlowLabels((prev) => {
        const next = { ...prev };
        wanted.forEach((r, i) => {
          next[r.name] = labels[i] ?? '';
        });
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs]);

  // Initialize filters from URL on mount
  useEffect(() => {
    const initialSearch = searchParams.get('q') ?? '';
    const initialStatus = searchParams.get('status') ?? 'all';
    const initialAgents = searchParams.get('agents') ?? 'all';
    const initialRange = searchParams.get('range') ?? DEFAULT_RANGE;

    if (initialSearch) {
      setSearch(initialSearch);
    }
    if (initialStatus && initialStatus !== (filters.status || 'all')) {
      setFilter('status', initialStatus);
    }
    if (initialAgents && initialAgents !== (filters.agents || 'all')) {
      setFilter('agents', initialAgents);
    }
    if (initialRange && initialRange !== (filters.range || DEFAULT_RANGE)) {
      setFilter('range', initialRange);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateSearchParams = (next: { q?: string; status?: string; agents?: string; range?: string }) => {
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);

      if (next.q !== undefined) {
        if (next.q) sp.set('q', next.q);
        else sp.delete('q');
      }

      if (next.status !== undefined) {
        if (next.status && next.status !== 'all') sp.set('status', next.status);
        else sp.delete('status');
      }

      if (next.agents !== undefined) {
        if (next.agents && next.agents !== 'all') sp.set('agents', next.agents);
        else sp.delete('agents');
      }

      if (next.range !== undefined) {
        if (next.range && next.range !== DEFAULT_RANGE) sp.set('range', next.range);
        else sp.delete('range');
      }

      return sp;
    });
  };

  // Fetch agents on mount
  useEffect(() => {
    async function fetchAgents() {
      try {
        const agentList = await db.getDocList(doctype.Agent, {
          fields: ['name'],
          limit: 10000, // Fetch all agents
          orderBy: { field: 'name', order: 'asc' },
        });
        setAgents(agentList as Array<{ name: string }>);
      } catch (error) {
        handleFrappeError(error, 'Error fetching agents');
        setAgents([]);
      }
    }
    fetchAgents();
  }, []);

  const statusOptions = [
    { label: 'All status', value: 'all' },
    { label: 'Started', value: 'Started' },
    { label: 'Queued', value: 'Queued' },
    { label: 'Success', value: 'Success' },
    { label: 'Failed', value: 'Failed' },
  ];

  const agentOptions = useMemo(() => {
    const items = agents.map((agent) => ({
      value: agent.name,
      label: agent.name,
    }));
    return [{ label: 'All agents', value: 'all' }, ...items];
  }, [agents]);

  const selectedAgentValue = filters.agents || 'all';
  const selectedRange = filters.range || DEFAULT_RANGE;

  // The metric strip mirrors the same Time filter as the data grid, so
  // "Last 24h" narrows both together. "All time" can't be sent unbounded —
  // the analytics API caps a window at 93 days — so it's approximated with
  // a 90-day lookback instead.
  const analyticsFromDate = useMemo(() => {
    const rangeMs = TIME_RANGE_MS[selectedRange];
    const ms = rangeMs ?? 90 * 24 * 60 * 60 * 1000;
    return new Date(Date.now() - ms).toISOString();
  }, [selectedRange]);
  const analyticsGranularity: 'hour' | 'day' = selectedRange === '24h' ? 'hour' : 'day';

  // Define table columns
  const columns = useMemo<ColumnDef<AgentRunDoc>[]>(
    () => [
      {
        accessorKey: 'agent',
        header: ({ column }) => {
          return (
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
            >
              Agent
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => {
          const flowLabel = flowLabels[row.original.name];
          const agent = row.getValue('agent') as string | undefined;
          if (flowLabel) {
            return (
              <div data-testid={`execution-flow-label-${row.original.name}`}>
                <div className="font-body text-[13px] font-medium text-ink">{flowLabel}</div>
                {agent && <div className="font-body text-[12px] text-steel">{agent}</div>}
              </div>
            );
          }
          return <div className="font-body text-[13px] font-medium text-ink">{agent || (row.original.flow_run ? 'Flow step (flow no longer exists)' : 'Unknown Agent')}</div>;
        },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => {
          return (
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
            >
              Run ID
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => (
          <div className="font-mono text-[12px] text-steel">{row.getValue('name')}</div>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => {
          const status = row.getValue('status') as string;
          const { variant, label } = getRunStatusDot(status);
          return (
            <div className="flex items-center gap-2">
              <StatusDot variant={variant} />
              <span className="font-body text-[13px] text-steel">{label}</span>
            </div>
          );
        },
      },
      {
        accessorKey: 'cost',
        header: 'Cost',
        cell: ({ row }) => {
          const cost = row.original.cost;
          return (
            <div className="text-right font-mono text-[12px] tabular-nums text-steel">
              {typeof cost === 'number' ? `$${cost.toFixed(6)}` : 'Not available'}
            </div>
          );
        },
      },
      {
        accessorKey: 'cached_tokens',
        header: ({ column }) => {
          return (
            <div className="flex justify-end">
              <Button
                variant="ghost"
                onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
                className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
              >
                Cached tokens
                <ArrowUpDown className="ml-2 h-4 w-4" />
              </Button>
            </div>
          );
        },
        cell: ({ row }) => {
          const cached = row.original.cached_tokens;
          const isZero = !cached;
          return (
            <div
              className={cn(
                'text-right font-mono text-[12px] tabular-nums',
                isZero ? 'text-steel-soft/60' : 'text-steel'
              )}
            >
              {typeof cached === 'number' ? cached.toLocaleString() : '0'}
            </div>
          );
        },
        sortingFn: (rowA, rowB) => {
          const valA = rowA.original.cached_tokens ?? 0;
          const valB = rowB.original.cached_tokens ?? 0;
          return valA - valB;
        },
      },
      {
        id: 'duration',
        header: () => <div className="text-right">Duration</div>,
        cell: ({ row }) => {
          const duration = calculateDuration(row.original.start_time ?? null, row.original.end_time ?? null);
          return <div className="text-right font-mono text-[12px] tabular-nums text-steel">{duration}</div>;
        },
      },
      {
        id: 'started',
        header: ({ column }) => {
          return (
            <div className="flex justify-end">
              <Button
                variant="ghost"
                onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
                className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
              >
                Started
                <ArrowUpDown className="ml-2 h-4 w-4" />
              </Button>
            </div>
          );
        },
        cell: ({ row }) => {
          const timeAgo = formatTimeAgo(row.original.start_time ?? null);
          return <div className="text-right font-mono text-[12px] tabular-nums text-steel">{timeAgo}</div>;
        },
        sortingFn: (rowA, rowB) => {
          const timeA = rowA.original.start_time ? new Date(rowA.original.start_time).getTime() : 0;
          const timeB = rowB.original.start_time ? new Date(rowB.original.start_time).getTime() : 0;
          return timeA - timeB;
        },
      },
    ],
    [flowLabels]
  );

  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data: runs,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: {
      sorting,
    },
  });

  return (
    <PageFrame
      title="Executions"
      badge={<ExperimentalBadge />}
      filters={
        <FilterBar
          searchPlaceholder="Search executions using Agent Name"
          searchValue={search}
          onSearchChange={(value) => {
            setSearch(value);
            updateSearchParams({ q: value });
          }}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: statusOptions,
              onChange: (value) => {
                setFilter('status', value);
                updateSearchParams({ status: value });
              },
            },
            {
              label: 'Time',
              value: selectedRange,
              options: TIME_RANGE_OPTIONS,
              onChange: (value) => {
                setFilter('range', value);
                updateSearchParams({ range: value });
              },
            },
          ]}
          actions={
            <div className="w-full sm:w-48">
              <Combobox
                options={agentOptions}
                value={selectedAgentValue}
                onValueChange={(value) => {
                  if (!value || value === 'all') {
                    setFilter('agents', 'all');
                    updateSearchParams({ agents: 'all' });
                  } else {
                    setFilter('agents', value);
                    updateSearchParams({ agents: value });
                  }
                }}
                placeholder="Filter by agent..."
                emptyText="No agents found."
                searchPlaceholder="Search agents..."
              />
            </div>
          }
        />
      }
    >
      {/*
        One bordered/rounded card holds the metric strip and the data grid —
        runs are scanned, not read, so the numbers and the rows they roll up
        live in the same frame instead of two separately-bordered blocks.
      */}
      <div className="w-full rounded-lg border border-line bg-panel overflow-hidden">
        <ExecutionAnalyticsDashboard fromDate={analyticsFromDate} granularity={analyticsGranularity} listedRunCount={initialLoading ? undefined : total} />
        <div className="border-t border-line">
          {initialLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
            </div>
          ) : runs.length === 0 ? (
            !!search ||
            (filters.status && filters.status !== 'all') ||
            (filters.agents && filters.agents !== 'all') ||
            (filters.range && filters.range !== DEFAULT_RANGE) ? (
              <EmptyState
                variant="no-results"
                icon={Activity}
                title="No executions found"
                filterTerm={search}
                secondaryAction={{
                  label: 'Clear filters',
                  onClick: () => {
                    setSearch('');
                    setFilter('status', 'all');
                    setFilter('agents', 'all');
                    setFilter('range', DEFAULT_RANGE);
                    updateSearchParams({ q: '', status: 'all', agents: 'all', range: DEFAULT_RANGE });
                  },
                }}
              />
            ) : (
              <EmptyState
                variant="passive"
                icon={Activity}
                title="No executions"
                description="No agent runs have been recorded yet."
              />
            )
          ) : (
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => {
                      return (
                        <TableHead
                          key={header.id}
                          className={cn(RIGHT_ALIGNED_COLUMNS.has(header.column.id) && 'text-right')}
                        >
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                        </TableHead>
                      );
                    })}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.map((row) => (
                  <TableRow
                    key={row.id}
                    className="h-11 cursor-pointer hover:bg-paper-deep"
                    onClick={() => navigate(`/executions/${row.original.name}`)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell
                        key={cell.id}
                        className={cn(RIGHT_ALIGNED_COLUMNS.has(cell.column.id) && 'text-right')}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </div>

      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />

      {!hasMore && runs.length > 0 && (
        <div className="text-center py-4 text-sm text-steel">
          {total !== undefined ? `All ${total} executions` : 'No more executions to load'}
        </div>
      )}
    </PageFrame>
  );
}

const FLOW_RUN_STATUS_OPTIONS = [
  { label: 'All status', value: 'all' },
  { label: 'Queued', value: 'Queued' },
  { label: 'Running', value: 'Running' },
  { label: 'Waiting Approval', value: 'Waiting Approval' },
  { label: 'Waiting User', value: 'Waiting User' },
  { label: 'Success', value: 'Success' },
  { label: 'Failed', value: 'Failed' },
];

function getFlowRunStatusDot(status?: string): { variant: StatusDotVariant; label: string } {
  if (status === 'Success') return { variant: 'ok', label: status };
  if (status === 'Failed') return { variant: 'fail', label: status };
  if (status === 'Queued') return { variant: 'idle', label: status };
  return { variant: 'run', label: status || 'Running' };
}

/** The "Flow runs" tab: every Flow Run, newest first; a row opens the same Run details sheet as the flow canvas. */
function ExecutionsFlowRunsTab() {
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
  const headClass = 'font-mono text-[10px] uppercase tracking-widest text-steel-soft';

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
                      <div className="font-body text-[13px] font-medium text-ink">{run.flow_name}</div>
                      <div className="font-mono text-[11px] text-steel-soft">{run.name}</div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <StatusDot variant={variant} />
                        <span className="font-body text-[13px] text-steel">{label}</span>
                        {run.stale && <span className="font-body text-[11px] text-warning">Looks stuck</span>}
                      </div>
                    </TableCell>
                    <TableCell className="font-body text-[13px] text-steel">{run.trigger_type || 'Not available'}</TableCell>
                    <TableCell className="text-right font-mono text-[12px] tabular-nums text-steel">
                      {calculateDuration(run.started_at, run.completed_at)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-[12px] tabular-nums text-steel" title={formatTimeAgo(run.started_at)}>
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

/**
 * Merges the former `/executions` and `/analytics` routes into one page with
 * two sub-tabs, following the same URL-synced Tabs pattern used by
 * SkillFormPage's prompts/summary tabs. Tab state lives in `?tab=` so a link
 * like `/executions?tab=analytics` opens directly on the Analytics tab —
 * this is what lets a future task deep-link breakdown rows there.
 */
export default function Executions() {
  const [searchParams, setSearchParams] = useSearchParams();

  const tabFromUrl = searchParams.get('tab');
  const activeTab: ExecutionsTab =
    tabFromUrl && (EXECUTIONS_TABS as readonly string[]).includes(tabFromUrl)
      ? (tabFromUrl as ExecutionsTab)
      : DEFAULT_TAB;

  const handleTabChange = (value: string) => {
    setSearchParams(
      (prev) => {
        const sp = new URLSearchParams(prev);
        if (value === DEFAULT_TAB) {
          sp.delete('tab');
        } else {
          sp.set('tab', value);
        }
        return sp;
      },
      { replace: true }
    );
  };

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange} className="h-full flex flex-col">
      <TabsList className="mx-6 mt-4 w-fit shrink-0">
        <TabsTrigger value="runs">Runs</TabsTrigger>
        <TabsTrigger value="flow-runs" data-testid="executions-tab-flow-runs">Flow runs</TabsTrigger>
        <TabsTrigger value="analytics">Analytics</TabsTrigger>
      </TabsList>
      <TabsContent value="runs" className="flex-1 min-h-0">
        <ExecutionsRunsTab />
      </TabsContent>
      <TabsContent value="flow-runs" className="flex-1 min-h-0">
        <ExecutionsFlowRunsTab />
      </TabsContent>
      <TabsContent value="analytics" className="flex-1 min-h-0">
        <AnalyticsPage />
      </TabsContent>
    </Tabs>
  );
}
