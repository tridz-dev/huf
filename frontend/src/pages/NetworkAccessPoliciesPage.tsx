import { useMemo, useState } from 'react';
import { ArrowUpDown, Loader2, Plus, ShieldCheck } from 'lucide-react';
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
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
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
  getNetworkAccessPolicies,
  type NetworkAccessPolicyDoc,
  type GetNetworkAccessPoliciesParams,
} from '@/services/networkAccessPolicyApi';
import { formatTimeAgo } from '@/utils/time';

interface NetworkAccessPolicyListParams extends GetNetworkAccessPoliciesParams {
  [key: string]: unknown;
}

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

export function NetworkAccessPoliciesPage() {
  const navigate = useNavigate();
  const [sorting, setSorting] = useState<SortingState>([]);

  const {
    items: policies,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
  } = useInfiniteScroll<NetworkAccessPolicyListParams, NetworkAccessPolicyDoc>({
    fetchFn: async (params) => {
      const response = await getNetworkAccessPolicies({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
      });

      return {
        data: response.items,
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
  });

  const columns = useMemo<ColumnDef<NetworkAccessPolicyDoc>[]>(
    () => [
      {
        accessorKey: 'policy_name',
        header: ({ column }) => <SortHeader column={column} label="Policy name" />,
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-steel-soft shrink-0" strokeWidth={1.6} />
            <div className="font-body text-[13px] font-semibold text-ink">
              {row.original.policy_name || row.original.name}
            </div>
          </div>
        ),
      },
      {
        id: 'rules',
        header: 'Rules',
        cell: ({ row }) => (
          <span className="font-mono text-[12px] text-steel">
            {(row.original.rules || []).length} rule{(row.original.rules || []).length === 1 ? '' : 's'}
          </span>
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
    data: policies,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  return (
    <PageFrame
      title="Network access policies"
      filters={
        <FilterBar
          searchPlaceholder="Search network access policies..."
          searchValue={search}
          onSearchChange={setSearch}
          primaryAction={{
            label: 'New policy',
            icon: <Plus className="h-4 w-4" />,
            onClick: () => navigate('/network-policies/new'),
          }}
        />
      }
    >
      <div className="w-full">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : policies.length === 0 ? (
          search ? (
            <EmptyState
              variant="no-results"
              icon={ShieldCheck}
              title="No network access policies found"
              filterTerm={search}
              secondaryAction={{
                label: 'Clear search',
                onClick: () => setSearch(''),
              }}
            />
          ) : (
            <EmptyState
              variant="create"
              icon={ShieldCheck}
              title="No network access policies"
              description="Add a policy to control which hosts and ports are reachable."
              action={{ label: 'New policy', onClick: () => navigate('/network-policies/new') }}
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
                    onClick={() => navigate(`/network-policies/${row.original.name}`)}
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

      {!hasMore && policies.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} network access policies` : 'No more policies to load'}
        </div>
      )}
    </PageFrame>
  );
}

export default NetworkAccessPoliciesPage;
