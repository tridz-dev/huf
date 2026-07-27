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
} from '@tanstack/react-table';
import { FilterBar, LoadMoreButton, PageLayout } from '@/components/dashboard';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Combobox } from '@/components/ui/combobox';
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

function getStatusVariant(disabled?: 0 | 1): 'success' | 'secondary' {
  return disabled === 1 ? 'secondary' : 'success';
}

function getApprovalBadgeVariant(approvalMode?: string): 'default' | 'outline' | 'destructive' {
  switch (approvalMode) {
    case 'Auto Approve':
      return 'outline';
    case 'Ask Every Time':
      return 'default';
    case 'Never Allow':
      return 'destructive';
    default:
      return 'outline';
  }
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
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            className="h-8 px-2"
          >
            Profile Name
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => (
          <div className="flex items-center gap-2 font-medium">
            <ShieldCheck className="h-4 w-4 text-primary shrink-0" />
            <span>{row.original.profile_name || row.original.name}</span>
            {row.original.is_builtin === 1 && (
              <Badge variant="outline" className="text-xs">
                Built-in
              </Badge>
            )}
          </div>
        ),
      },
      {
        accessorKey: 'approval_mode',
        header: 'Approval Mode',
        cell: ({ row }) => (
          <Badge variant={getApprovalBadgeVariant(row.original.approval_mode)}>
            {row.original.approval_mode || 'Ask Every Time'}
          </Badge>
        ),
      },
      {
        accessorKey: 'filesystem_policy',
        header: 'Filesystem Policy',
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5 text-sm text-steel">
            <HardDrive className="h-3.5 w-3.5" />
            <span>{row.original.filesystem_policy || 'None'}</span>
          </div>
        ),
      },
      {
        id: 'limits',
        header: 'Resource Limits',
        cell: ({ row }) => (
          <div className="flex items-center gap-2 text-xs text-steel">
            <Cpu className="h-3.5 w-3.5" />
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
          <Badge variant={getStatusVariant(row.original.disabled)}>
            {row.original.disabled === 1 ? 'Disabled' : 'Active'}
          </Badge>
        ),
      },
      {
        id: 'modified',
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            className="h-8 px-2"
          >
            Modified
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => (
          <div className="text-sm text-steel">{formatTimeAgo(row.original.modified ?? null)}</div>
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
    { label: 'All Status', value: 'all' },
    { label: 'Active', value: 'enabled' },
    { label: 'Disabled', value: 'disabled' },
  ];

  return (
    <PageLayout
      subtitle="Manage sandboxed code execution environments, resource limits, and approval policies."
      filters={
        <FilterBar
          searchPlaceholder="Search execution profiles..."
          searchValue={search}
          onSearchChange={setSearch}
          actions={
            <div className="w-full sm:w-48">
              <Combobox
                options={statusOptions}
                value={filters.status || 'all'}
                onValueChange={(value) => setFilter('status', value || 'all')}
                placeholder="Status"
              />
            </div>
          }
        />
      }
    >
      <div className="w-full">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : (
          <div className="overflow-hidden rounded-none border">
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
                {table.getRowModel().rows.length ? (
                  table.getRowModel().rows.map((row) => (
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
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      <div className="font-body text-steel">No Execution Profiles found.</div>
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

      {!hasMore && profiles.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} execution profiles` : 'No more profiles to load'}
        </div>
      )}
    </PageLayout>
  );
}

export default ExecutionProfilesPage;
