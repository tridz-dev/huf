import { useState, useEffect, useMemo } from 'react';
import { ArrowUpDown, Loader2 } from 'lucide-react';
import { FilterBar, PageLayout, LoadMoreButton } from '@/components/dashboard';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getAgentRuns, type AgentRunDoc } from '@/services/agentRunApi';
import { formatTimeAgo, calculateDuration } from '@/utils/time';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { getAgentRunStatusVariant } from '@/utils/status';
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
        status: params.status as any,
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
              className="h-8 px-2"
            >
              Agent
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => (
          <div className="font-medium">{row.getValue('agent') || 'Unknown Agent'}</div>
        ),
      },
      {
        accessorKey: 'name',
        header: ({ column }) => {
          return (
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2"
            >
              Run ID
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => (
          <div className="font-mono text-sm text-muted-foreground">{row.getValue('name')}</div>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => {
          const status = row.getValue('status') as string;
          return (
            <Badge variant={getAgentRunStatusVariant(status)}>
              {status || 'Unknown'}
            </Badge>
          );
        },
      },
      {
        id: 'duration',
        header: 'Duration',
        cell: ({ row }) => {
          const duration = calculateDuration(row.original.start_time ?? null, row.original.end_time ?? null);
          return <div className="text-sm">{duration}</div>;
        },
      },
      {
        id: 'started',
        header: ({ column }) => {
          return (
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2"
            >
              Started
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => {
          const timeAgo = formatTimeAgo(row.original.start_time ?? null);
          return <div className="text-sm text-muted-foreground">{timeAgo}</div>;
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
    <PageLayout
      subtitle="View all executions of your Agents"
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
            <div className="w-48">
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
      <div className="w-full">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border">
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
                {table.getRowModel().rows?.length ? (
                  table.getRowModel().rows.map((row) => (
                    <TableRow
                      key={row.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/executions/${row.original.name}`)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      <div className="text-muted-foreground">No executions found.</div>
                    </TableCell>
                  </TableRow>
                )}
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
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} executions` : 'No more executions to load'}
        </div>
      )}
    </PageLayout>
  );
}
