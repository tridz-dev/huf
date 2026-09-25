import { useMemo, useState } from 'react';
import { ArrowUpDown, Loader2, Cpu, ShieldCheck } from 'lucide-react';
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
  getSubscriptionRuntimes,
  type SubscriptionRuntimeDoc,
  type GetSubscriptionRuntimesParams,
} from '@/services/subscriptionRuntimeApi';
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

const AUTH_STATUS_LABELS: Record<string, string> = {
  unknown: 'Unknown',
  ready: 'Ready',
  required: 'Required',
  waiting_user: 'Waiting on you',
  verifying: 'Verifying',
  failed: 'Failed',
};

export function SubscriptionRuntimesPage() {
  const navigate = useNavigate();
  const [sorting, setSorting] = useState<SortingState>([]);

  const {
    items: runtimes,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    filters,
    setFilter,
  } = useInfiniteScroll<GetSubscriptionRuntimesParams, SubscriptionRuntimeDoc>({
    fetchFn: async (params) => {
      const response = await getSubscriptionRuntimes({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: (params.status as GetSubscriptionRuntimesParams['status']) ?? 'all',
      });

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

  const columns = useMemo<ColumnDef<SubscriptionRuntimeDoc>[]>(
    () => [
      {
        accessorKey: 'runtime_name',
        header: ({ column }) => <SortHeader column={column} label="Runtime name" />,
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-steel-soft shrink-0" strokeWidth={1.6} />
            <div>
              <div className="font-body text-[13px] font-semibold text-ink">
                {row.original.runtime_name}
              </div>
              <div className="font-mono text-[11px] text-steel-soft">{row.original.provider_family}</div>
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'provider_family',
        header: 'Provider',
        cell: ({ row }) => (
          <span className="font-mono text-[12px] text-steel">{row.original.provider_family}</span>
        ),
      },
      {
        accessorKey: 'transport_type',
        header: 'Transport',
        cell: ({ row }) => (
          <span className="font-mono text-[12px] text-steel">{row.original.transport_type}</span>
        ),
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
        id: 'auth_status',
        header: 'Auth Status',
        cell: ({ row }) => {
          const status = row.original.auth_status || 'unknown';
          return (
            <div className="flex items-center gap-2">
              <ShieldCheck
                className={`h-3.5 w-3.5 ${status === 'ready' ? 'text-steel' : 'text-steel-soft'}`}
                strokeWidth={1.6}
              />
              <span className="font-body text-[13px] text-steel">
                {AUTH_STATUS_LABELS[status] || status}
              </span>
            </div>
          );
        },
      },
      {
        id: 'last_tested_on',
        header: ({ column }) => <SortHeader column={column} label="Last Tested" />,
        cell: ({ row }) => {
          const status = row.original.last_test_status;
          if (!row.original.last_tested_on) {
            return <span className="font-mono text-[11px] text-steel-soft">Never tested</span>;
          }
          return (
            <div className="flex items-center gap-2">
              <StatusDot variant={status === 'Success' ? 'ok' : 'fail'} />
              <span className="font-mono text-[12px] text-steel">
                {formatTimeAgo(row.original.last_tested_on)}
              </span>
            </div>
          );
        },
        sortingFn: (rowA, rowB) => {
          const timeA = rowA.original.last_tested_on ? new Date(rowA.original.last_tested_on).getTime() : 0;
          const timeB = rowB.original.last_tested_on ? new Date(rowB.original.last_tested_on).getTime() : 0;
          return timeA - timeB;
        },
      },
    ],
    []
  );

  const table = useReactTable({
    data: runtimes,
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
      title="Subscription runtimes"
      actions={
        <Button variant="display" onClick={() => navigate('/subscription-runtimes/new')}>
          New runtime
        </Button>
      }
      filters={
        <FilterBar
          searchPlaceholder="Search subscription runtimes..."
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
        ) : runtimes.length === 0 ? (
          !!search || (filters.status && filters.status !== 'all') ? (
            <EmptyState
              variant="no-results"
              icon={Cpu}
              title="No subscription runtimes found"
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
              icon={Cpu}
              title="No subscription runtimes"
              description="Add a runtime to let agents use a signed-in CLI subscription."
              action={{ label: 'New runtime', onClick: () => navigate('/subscription-runtimes/new') }}
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
                    onClick={() => navigate(`/subscription-runtimes/${row.original.name}`)}
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

      {!hasMore && runtimes.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} subscription runtimes` : 'No more runtimes to load'}
        </div>
      )}
    </PageFrame>
  );
}

export default SubscriptionRuntimesPage;
