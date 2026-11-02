import { useState, useEffect, useMemo } from 'react';
import { Activity, ArrowUpDown, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { StatusPill, type StatusKind } from '@/components/common/StatusPill';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useExecutionsAccess } from '@/hooks/permissions/useExecutionsAccess';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import type { AgentRunDoc } from '@/services/agentRunApi';
import { formatTimeAgo, calculateDuration } from '@/utils/time';
import { useSiteTimezone } from '@/lib/serverTime';
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
import { Tabs, TabsContent } from '@/components/ui/tabs';
import AnalyticsPage from '@/pages/AnalyticsPage';
import { ExecutionsFlowRunsTab } from '@/components/executions/FlowRunsTab';
import { ExecutionsTabsBar } from '@/components/executions/ExecutionsTabsBar';
import { DEFAULT_RANGE, TIME_RANGE_MS, TIME_RANGE_OPTIONS } from '@/components/executions/executionsRange';
import { fetchAgentRunsPage } from '@/components/executions/fetchAgentRunsPage';
import { useFlowStepLabelsFor } from '@/hooks/flow/useFlowStepLabelsFor';

/** Sub-tabs hosted on this page — kept in the URL so a link like
 * `/executions?tab=analytics` opens directly on the Analytics tab. */
const EXECUTIONS_TABS = ['runs', 'flow-runs', 'analytics'] as const;
type ExecutionsTab = (typeof EXECUTIONS_TABS)[number];
const DEFAULT_TAB: ExecutionsTab = 'runs';

/** Columns whose values are numeric/temporal and read better right-aligned with tabular figures. */
const RIGHT_ALIGNED_COLUMNS = new Set(['cost', 'cached_tokens', 'duration', 'started']);

function agentRunStatusKind(status?: string): StatusKind {
  const normalized = status?.toLowerCase() || '';
  if (normalized === 'success') return 'finished';
  if (normalized === 'failed') return 'failed';
  if (normalized === 'queued') return 'queued';
  return 'running';
}

/** The "Runs" tab — this is the original Executions page body, unchanged. */
function ExecutionsRunsTab() {
  const { canSeeAnalytics } = useExecutionsAccess(); // analytics are only for people who see all agents
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
    fetchFn: fetchAgentRunsPage,
    initialParams: {},
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
  });

  // Runs made by a flow step carry no agent of their own: name them "Flow: <flow name> > <step title>".
  const flowLabels = useFlowStepLabelsFor(runs);

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
    { label: 'All statuses', value: 'all' },
    { label: 'Queued', value: 'Queued' },
    { label: 'Running', value: 'Started' },
    { label: 'Finished', value: 'Success' },
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
              className="h-8 px-2 font-mono text-eyebrow uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
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
                <div className="font-body text-ui-text text-ink">{flowLabel}</div>
                {agent && <div className="font-body text-xs text-steel">{agent}</div>}
              </div>
            );
          }
          return <div className="font-body text-ui-text text-ink">{agent || (row.original.flow_run ? 'Flow step (flow no longer exists)' : 'Unknown Agent')}</div>;
        },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => {
          return (
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2 font-mono text-eyebrow uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
            >
              Run ID
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => (
          <div className="font-mono text-xs text-steel">{row.getValue('name')}</div>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => {
          const status = row.getValue('status') as string;
          return <StatusPill kind={agentRunStatusKind(status)} />;
        },
      },
      {
        accessorKey: 'cost',
        header: 'Cost',
        cell: ({ row }) => {
          const cost = row.original.cost;
          return (
            <div className="text-right font-mono text-xs tabular-nums text-steel">
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
                className="h-8 px-2 font-mono text-eyebrow uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
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
                'text-right font-mono text-xs tabular-nums',
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
          return <div className="text-right font-mono text-xs tabular-nums text-steel">{duration}</div>;
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
                className="h-8 px-2 font-mono text-eyebrow uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
              >
                Started
                <ArrowUpDown className="ml-2 h-4 w-4" />
              </Button>
            </div>
          );
        },
        cell: ({ row }) => {
          const timeAgo = formatTimeAgo(row.original.start_time ?? null);
          return <div className="text-right font-mono text-xs tabular-nums text-steel">{timeAgo}</div>;
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
      tabs={<ExecutionsTabsBar active="runs" />}
      filters={
        <FilterBar
          searchPlaceholder="Search agent runs by agent name"
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
        {canSeeAnalytics && <ExecutionAnalyticsDashboard fromDate={analyticsFromDate} granularity={analyticsGranularity} listedRunCount={initialLoading ? undefined : total} />}
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

/**
 * Merges the former `/executions` and `/analytics` routes into one page with
 * two sub-tabs, following the same URL-synced Tabs pattern used by
 * SkillFormPage's prompts/summary tabs. Tab state lives in `?tab=` so a link
 * like `/executions?tab=analytics` opens directly on the Analytics tab —
 * this is what lets a future task deep-link breakdown rows there.
 */
export default function Executions() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { canSeeAnalytics, canSeeFlowRuns, allows } = useExecutionsAccess();

  const tabFromUrl = searchParams.get('tab');
  const requestedTab = tabFromUrl && (EXECUTIONS_TABS as readonly string[]).includes(tabFromUrl) ? (tabFromUrl as ExecutionsTab) : DEFAULT_TAB;
  const activeTab: ExecutionsTab = allows(requestedTab) ? requestedTab : DEFAULT_TAB; // a tab this role cannot read falls back to the runs

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
      <TabsContent value="runs" className="flex-1 min-h-0">
        <ExecutionsRunsTab />
      </TabsContent>
      {canSeeFlowRuns && <TabsContent value="flow-runs" className="flex-1 min-h-0"><ExecutionsFlowRunsTab /></TabsContent>}
      {canSeeAnalytics && <TabsContent value="analytics" className="flex-1 min-h-0"><AnalyticsPage tabs={<ExecutionsTabsBar active="analytics" />} /></TabsContent>}
    </Tabs>
  );
}
