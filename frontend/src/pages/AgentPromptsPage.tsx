import { useMemo, useState } from 'react';
import { ArrowUpDown, FileText, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
  getAgentPrompts,
  type AgentPromptDoc,
  type GetAgentPromptsParams,
} from '@/services/agentPromptApi';
import { formatTimeAgo } from '@/utils/time';
import { PromptLibraryTabs } from '@/components/agent/PromptLibraryTabs';

function getStatusVariant(enabled: 0 | 1): 'success' | 'secondary' {
  return enabled === 1 ? 'success' : 'secondary';
}

export function AgentPromptsPage() {
  const navigate = useNavigate();
  const [sorting, setSorting] = useState<SortingState>([]);

  const {
    items: prompts,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    filters,
    setFilter,
  } = useInfiniteScroll<GetAgentPromptsParams, AgentPromptDoc>({
    fetchFn: async (params) => {
      const response = await getAgentPrompts({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: (params.status as GetAgentPromptsParams['status']) ?? 'all',
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

  const columns = useMemo<ColumnDef<AgentPromptDoc>[]>(
    () => [
      {
        accessorKey: 'title',
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            className="h-8 px-2"
          >
            Title
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => <div className="font-medium">{row.original.title || row.original.name}</div>,
      },
      {
        accessorKey: 'slug',
        header: 'Slug',
        cell: ({ row }) => <div className="text-sm text-steel">{row.original.slug || '-'}</div>,
      },
      {
        accessorKey: 'version',
        header: 'Version',
        cell: ({ row }) => <div>v{row.original.version ?? 1}</div>,
      },
      {
        accessorKey: 'visibility',
        header: 'Visibility',
        cell: ({ row }) => <div>{row.original.visibility || 'Private'}</div>,
      },
      {
        accessorKey: 'is_active',
        header: 'Status',
        cell: ({ row }) => (
          <Badge variant={getStatusVariant(row.original.is_active)}>
            {row.original.is_active === 1 ? 'Active' : 'Inactive'}
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
    data: prompts,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  const statusOptions = [
    { label: 'All status', value: 'all' },
    { label: 'Active', value: 'active' },
    { label: 'Inactive', value: 'inactive' },
  ];

  return (
    <PageFrame
      title="Prompts"
      actions={<Button onClick={() => navigate('/prompts/new')}>New prompt</Button>}
      filters={
        <FilterBar
          searchPlaceholder="Search prompts..."
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
      <PromptLibraryTabs />
      <div className="w-full">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : prompts.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No prompts"
            description="Create a prompt template to share across agents."
            action={{ label: 'New prompt', onClick: () => navigate('/prompts/new') }}
          />
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
                    onClick={() => navigate(`/prompts/${row.original.name}`)}
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

      {!hasMore && prompts.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} prompts` : 'No more prompts to load'}
        </div>
      )}
    </PageFrame>
  );
}

export default AgentPromptsPage;
