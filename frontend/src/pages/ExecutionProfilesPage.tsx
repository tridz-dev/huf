import { useMemo, useState } from 'react';
import { ArrowUpDown, Loader2, ShieldCheck, HardDrive, Cpu } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
  HeaderContext,
} from '@tanstack/react-table';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, StatusDot, EmptyState } from '@/components/dashboard';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import {
  getExecutionProfiles,
  type ExecutionProfileDoc,
  type GetExecutionProfilesParams,
} from '@/services/executionProfileApi';
import { formatTimeAgo } from '@/utils/time';

function SortHeader<TData>({ column, label }: { column: HeaderContext<TData, unknown>['column']; label: string }) {
  return (
    <Button
      variant="ghost"
      onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
      className="h-8 px-2 font-body text-[13px] font-medium text-steel hover:text-ink hover:bg-paper-deep"
    >
      {label}
      <ArrowUpDown className="ml-2 h-3.5 w-3.5" />
    </Button>
  );
}

export function ExecutionProfilesPage() {
  const navigate = useNavigate();
  const [sorting, setSorting] = useState<SortingState>([]);

  const {
    items: profiles,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    filters,
    setFilter,
  } = useInfiniteScroll<GetExecutionProfilesParams, ExecutionProfileDoc>({
    fetchFn: async (params) => {
      const response = await getExecutionProfiles({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: (params.status as GetExecutionProfilesParams['status']) ?? 'all',
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
    initialParams: { status: 'all' },
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
  });

  const columns = useMemo<ColumnDef<ExecutionProfileDoc>[]>(
    () => [
      {
        accessorKey: 'profile_name',
        header: ({ column }) => <SortHeader column={column} label="Profile name" />,
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-steel-soft shrink-0" strokeWidth={1.6} />
            <div>
              <div className="font-body text-[13px] font-semibold text-ink">
                {row.original.profile_name || row.original.name}
              </div>
              {row.original.is_builtin === 1 && (
                <span className="font-mono text-[11px] text-steel-soft">Built-in</span>
              )}
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'approval_mode',
        header: 'Approval Mode',
        cell: ({ row }) => (
          <span className="font-mono text-[12px] text-steel">
            {row.original.approval_mode || 'Ask Every Time'}
          </span>
        ),
      },
      {
        accessorKey: 'filesystem_policy',
        header: 'Filesystem Policy',
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5 font-mono text-[12px] text-steel">
            <HardDrive className="h-3.5 w-3.5" strokeWidth={1.6} />
            <span>{row.original.filesystem_policy || 'None'}</span>
          </div>
        ),
      },
      {
        id: 'limits',
        header: 'Resource Limits',
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5 font-mono text-[12px] text-steel">
            <Cpu className="h-3.5 w-3.5" strokeWidth={1.6} />
            <span>
              {row.original.max_wall_time_s ?? 30}s / {row.original.max_memory_mb ?? 256}MB
            </span>
          </div>
        ),
      },
      {
        accessorKey: 'disabled',
        header: 'Status',
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <StatusDot variant={row.original.disabled === 1 ? 'idle' : 'ok'} />
            <span className="font-body text-[13px] text-steel">
              {row.original.disabled === 1 ? 'Disabled' : 'Active'}
            </span>
          </div>
        ),
      },
      {
        id: 'modified',
        header: ({ column }) => <SortHeader column={column} label="Modified" />,
        cell: ({ row }) => (
          <div className="font-mono text-[12px] text-steel">{formatTimeAgo(row.original.modified ?? null)}</div>
        ),
        sortingFn: (rowA, rowB) => {
          const timeA = rowA.original.modified ? new Date(rowA.original.modified).getTime() : 0;
          const timeB = rowB.original.modified ? new Date(rowB.original.modified).getTime() : 0;
          return timeA - timeB;
        },
      },
    ],
    []
  );

  const table = useReactTable({
    data: profiles,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  const statusOptions = [
    { label: 'All status', value: 'all' },
    { label: 'Active', value: 'enabled' },
    { label: 'Disabled', value: 'disabled' },
  ];

  return (
    <PageFrame
      title="Execution profiles"
      filters={
        <FilterBar
          searchPlaceholder="Search execution profiles..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: statusOptions,
              onChange: (value) => setFilter('status', value || 'all'),
              placeholder: 'All',
            },
          ]}
        />
      }
    >
      <div className="w-full">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : profiles.length === 0 ? (
          !!search || (filters.status && filters.status !== 'all') ? (
            <EmptyState
              variant="no-results"
              icon={ShieldCheck}
              title="No execution profiles found"
              filterTerm={search}
              secondaryAction={{
                label: 'Clear filters',
                onClick: () => {
                  setSearch('');
                  setFilter('status', 'all');
                },
              }}
            />
          ) : (
            <EmptyState
              variant="create"
              icon={ShieldCheck}
              title="No execution profiles"
              description="No execution profiles have been configured yet."
              action={{ label: 'New execution profile', onClick: () => navigate('/execution-profiles/new') }}
            />
          )
        ) : (
          <div className="border border-line bg-panel">
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
                    className="cursor-pointer hover:bg-paper-deep"
                    onClick={() => navigate(`/execution-profiles/${row.original.name}`)}
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

      {!hasMore && profiles.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} execution profiles` : 'No more profiles to load'}
        </div>
      )}
    </PageFrame>
  );
}

export default ExecutionProfilesPage;
