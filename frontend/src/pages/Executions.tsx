import { useState, useEffect, useMemo } from 'react';
import { Activity, ArrowUpDown, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { StatusDot, type StatusDotVariant } from '@/components/dashboard/ledger/LedgerSection';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getAgentRuns, type AgentRunDoc } from '@/services/agentRunApi';
import { formatTimeAgo, calculateDuration } from '@/utils/time';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
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

function getRunStatusDot(status?: string): { variant: StatusDotVariant; label: string } {
  const normalized = status?.toLowerCase() || '';
  if (normalized === 'success') return { variant: 'ok', label: status || 'Success' };
  if (normalized === 'failed') return { variant: 'fail', label: status || 'Failed' };
  if (normalized === 'queued') return { variant: 'idle', label: status || 'Queued' };
  return { variant: 'run', label: status || 'Started' };
}

export default function Executions() {
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
    { page?: number; limit?: number; start?: number; search?: string; status?: string; agents?: string },
    AgentRunDoc
  >({
    fetchFn: async (params) => {
      const response = await getAgentRuns({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status as 'Started' | 'Queued' | 'Success' | 'Failed' | 'all' | undefined,
        agents: params.agents ? params.agents.split(',').filter(Boolean) : undefined,
        filters: [["is_child","=","0"]]
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

  // Initialize filters from URL on mount
  useEffect(() => {
    const initialSearch = searchParams.get('q') ?? '';
    const initialStatus = searchParams.get('status') ?? 'all';
    const initialAgents = searchParams.get('agents') ?? 'all';

    if (initialSearch) {
      setSearch(initialSearch);
    }
    if (initialStatus && initialStatus !== (filters.status || 'all')) {
      setFilter('status', initialStatus);
    }
    if (initialAgents && initialAgents !== (filters.agents || 'all')) {
      setFilter('agents', initialAgents);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateSearchParams = (next: { q?: string; status?: string; agents?: string }) => {
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
    { label: 'All Status', value: 'all' },
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
    return [{ label: 'All Agents', value: 'all' }, ...items];
  }, [agents]);

  const selectedAgentValue = filters.agents || 'all';

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
        cell: ({ row }) => (
          <div className="font-body text-[13px] font-medium text-ink">{row.getValue('agent') || 'Unknown Agent'}</div>
        ),
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
        accessorKey: 'cached_tokens',
        header: ({ column }) => {
          return (
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
            >
              Cached tokens
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => {
          const cached = row.original.cached_tokens;
          return (
            <div className="font-mono text-[12px] text-steel">
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
        header: 'Duration',
        cell: ({ row }) => {
          const duration = calculateDuration(row.original.start_time ?? null, row.original.end_time ?? null);
          return <div className="font-mono text-[12px] text-steel">{duration}</div>;
        },
      },
      {
        id: 'started',
        header: ({ column }) => {
          return (
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft hover:text-ink hover:bg-paper-deep"
            >
              Started
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => {
          const timeAgo = formatTimeAgo(row.original.start_time ?? null);
          return <div className="font-mono text-[12px] text-steel">{timeAgo}</div>;
        },
        sortingFn: (rowA, rowB) => {
          const timeA = rowA.original.start_time ? new Date(rowA.original.start_time).getTime() : 0;
          const timeB = rowB.original.start_time ? new Date(rowB.original.start_time).getTime() : 0;
          return timeA - timeB;
        },
      },
    ],
    []
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
      subtitle="Inspect agent runs and their results."
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
      <ExecutionAnalyticsDashboard />
      <div className="w-full">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : runs.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No executions"
            description="No agent runs have been recorded yet."
          />
        ) : (
          <div className="border border-line bg-panel">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => {
                      return (
                        <TableHead key={header.id}>
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
                    className="cursor-pointer hover:bg-paper-deep"
                    onClick={() => navigate(`/executions/${row.original.name}`)}
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
          </div>
        )}
      </div>

      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />

      {!hasMore && runs.length > 0 && (
        <div className="text-center py-4 text-sm text-steel">
          {total !== undefined ? `Showing all ${total} executions` : 'No more executions to load'}
        </div>
      )}
    </PageFrame>
  );
}
