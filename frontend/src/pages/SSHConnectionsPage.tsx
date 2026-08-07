import { useMemo, useState } from 'react';
import { ArrowUpDown, Loader2, Terminal, Key } from 'lucide-react';
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
  getSSHConnections,
  type SSHConnectionDoc,
  type GetSSHConnectionsParams,
} from '@/services/sshConnectionApi';
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

export function SSHConnectionsPage() {
  const navigate = useNavigate();
  const [sorting, setSorting] = useState<SortingState>([]);

  const {
    items: connections,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    filters,
    setFilter,
  } = useInfiniteScroll<GetSSHConnectionsParams, SSHConnectionDoc>({
    fetchFn: async (params) => {
      const response = await getSSHConnections({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: (params.status as GetSSHConnectionsParams['status']) ?? 'all',
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

  const columns = useMemo<ColumnDef<SSHConnectionDoc>[]>(
    () => [
      {
        accessorKey: 'display_name',
        header: ({ column }) => <SortHeader column={column} label="Display name" />,
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-steel-soft shrink-0" strokeWidth={1.6} />
            <div>
              <div className="font-body text-[13px] font-semibold text-ink">
                {row.original.display_name || row.original.name}
              </div>
              <div className="font-mono text-[11px] text-steel-soft">
                {row.original.username}@{row.original.host}:{row.original.port || 22}
              </div>
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'auth_method',
        header: 'Auth Method',
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5 font-mono text-[12px] text-steel">
            <Key className="h-3.5 w-3.5" strokeWidth={1.6} />
            <span>{row.original.auth_method || 'Password'}</span>
          </div>
        ),
      },
      {
        id: 'host_key',
        header: 'Host Key',
        cell: ({ row }) => (
          <div>
            {row.original.host_key_fingerprint ? (
              <span className="font-mono text-[11px] text-steel">Pinned</span>
            ) : (
              <span className="font-mono text-[11px] text-steel-soft">Unenrolled</span>
            )}
          </div>
        ),
      },
      {
        id: 'test_status',
        header: 'Last Test',
        cell: ({ row }) => {
          const status = row.original.last_test_status;
          if (!status) return <span className="font-mono text-[11px] text-steel-soft">Never tested</span>;
          return (
            <div className="flex items-center gap-2">
              <StatusDot variant={status === 'Success' ? 'ok' : 'fail'} />
              <span className="font-body text-[13px] text-steel">{status}</span>
            </div>
          );
        },
      },
      {
        accessorKey: 'enabled',
        header: 'Status',
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <StatusDot variant={row.original.enabled === 1 ? 'ok' : 'idle'} />
            <span className="font-body text-[13px] text-steel">
              {row.original.enabled === 1 ? 'Enabled' : 'Disabled'}
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
    data: connections,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  const statusOptions = [
    { label: 'All status', value: 'all' },
    { label: 'Enabled', value: 'enabled' },
    { label: 'Disabled', value: 'disabled' },
  ];

  return (
    <PageFrame
      title="SSH connections"
      filters={
        <FilterBar
          searchPlaceholder="Search SSH connections..."
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
        ) : connections.length === 0 ? (
          !!search || (filters.status && filters.status !== 'all') ? (
            <EmptyState
              variant="no-results"
              icon={Terminal}
              title="No SSH connections found"
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
              icon={Terminal}
              title="No SSH connections"
              description="No SSH connections have been configured yet."
              action={{ label: 'New SSH connection', onClick: () => navigate('/ssh-connections/new') }}
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
                    onClick={() => navigate(`/ssh-connections/${row.original.name}`)}
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

      {!hasMore && connections.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} SSH connections` : 'No more connections to load'}
        </div>
      )}
    </PageFrame>
  );
}

export default SSHConnectionsPage;
