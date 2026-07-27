import { useMemo, useState } from 'react';
import { ArrowUpDown, Loader2, Terminal, Key, CheckCircle2, XCircle } from 'lucide-react';
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
  getSSHConnections,
  type SSHConnectionDoc,
  type GetSSHConnectionsParams,
} from '@/services/sshConnectionApi';
import { formatTimeAgo } from '@/utils/time';

function getStatusVariant(enabled?: 0 | 1): 'success' | 'secondary' {
  return enabled === 1 ? 'success' : 'secondary';
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
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            className="h-8 px-2"
          >
            Display Name
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => (
          <div className="flex items-center gap-2 font-medium">
            <Terminal className="h-4 w-4 text-primary shrink-0" />
            <span>{row.original.display_name || row.original.name}</span>
          </div>
        ),
      },
      {
        id: 'target',
        header: 'Host Target',
        cell: ({ row }) => (
          <div className="font-mono text-xs text-steel">
            {row.original.username}@{row.original.host}:{row.original.port || 22}
          </div>
        ),
      },
      {
        accessorKey: 'auth_method',
        header: 'Auth Method',
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5 text-xs text-steel">
            <Key className="h-3.5 w-3.5" />
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
              <Badge variant="outline" className="text-xs font-mono">
                Pinned
              </Badge>
            ) : (
              <span className="text-xs text-steel-soft">Unenrolled</span>
            )}
          </div>
        ),
      },
      {
        id: 'test_status',
        header: 'Last Test',
        cell: ({ row }) => {
          const status = row.original.last_test_status;
          if (!status) return <span className="text-xs text-steel-soft">Never tested</span>;
          return status === 'Success' ? (
            <div className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>Success</span>
            </div>
          ) : (
            <div className="flex items-center gap-1 text-xs text-rose-600 dark:text-rose-400">
              <XCircle className="h-3.5 w-3.5" />
              <span>Failed</span>
            </div>
          );
        },
      },
      {
        accessorKey: 'enabled',
        header: 'Status',
        cell: ({ row }) => (
          <Badge variant={getStatusVariant(row.original.enabled)}>
            {row.original.enabled === 1 ? 'Enabled' : 'Disabled'}
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
    data: connections,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  const statusOptions = [
    { label: 'All Status', value: 'all' },
    { label: 'Enabled', value: 'enabled' },
    { label: 'Disabled', value: 'disabled' },
  ];

  return (
    <PageLayout
      subtitle="Manage remote SSH host credentials, keys, and connection policies."
      filters={
        <FilterBar
          searchPlaceholder="Search SSH connections..."
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
                      onClick={() => navigate(`/ssh-connections/${row.original.name}`)}
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
                      <div className="font-body text-steel">No SSH Connections found.</div>
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

      {!hasMore && connections.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} SSH connections` : 'No more connections to load'}
        </div>
      )}
    </PageLayout>
  );
}

export default SSHConnectionsPage;
