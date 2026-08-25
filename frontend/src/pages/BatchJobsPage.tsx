import { useState, useMemo } from 'react';
import { Layers, Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { StatusDot, type StatusDotVariant } from '@/components/dashboard/ledger/LedgerSection';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { getBatchJobs } from '@/services/batchJobApi';
import type { BatchJobDoc } from '@/types/batchJob.types';
import { formatTimeAgo } from '@/utils/time';
import { cn } from '@/lib/utils';
import { BatchJobDetailDialog } from '@/components/batchJobs/BatchJobDetailDialog';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
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

const STATUS_OPTIONS = [
  { label: 'All status', value: 'all' },
  { label: 'Pending', value: 'Pending' },
  { label: 'Submitted', value: 'Submitted' },
  { label: 'In progress', value: 'In Progress' },
  { label: 'Completed', value: 'Completed' },
  { label: 'Failed', value: 'Failed' },
  { label: 'Cancelled', value: 'Cancelled' },
  { label: 'Expired', value: 'Expired' },
];

const PROVIDER_OPTIONS = [
  { label: 'All providers', value: 'all' },
  { label: 'OpenAI', value: 'OpenAI' },
  { label: 'Anthropic', value: 'Anthropic' },
  { label: 'Gemini', value: 'Gemini' },
];

/** Batch Job status -> the same ok/fail/idle/run dot vocabulary as Executions. */
function getBatchJobStatusDot(status?: string): { variant: StatusDotVariant; label: string } {
  const normalized = status?.toLowerCase() || '';
  if (normalized === 'completed') return { variant: 'ok', label: status || 'Completed' };
  if (normalized === 'failed' || normalized === 'expired') return { variant: 'fail', label: status || 'Failed' };
  if (normalized === 'cancelled') return { variant: 'idle', label: status || 'Cancelled' };
  if (normalized === 'pending') return { variant: 'idle', label: status || 'Pending' };
  return { variant: 'run', label: status || 'Submitted' };
}

/** Rough dollar estimate of what running this job instantly would have cost,
 * derived from the ~50% batch discount -- shown as "saved" alongside the
 * actual (already-discounted) estimated cost recorded on the job. */
function formatEstimatedSavings(estimatedCost?: number | null): string {
  if (typeof estimatedCost !== 'number') return 'Not available';
  return `$${estimatedCost.toFixed(4)}`;
}

export default function BatchJobsPage() {
  const [selectedJob, setSelectedJob] = useState<BatchJobDoc | null>(null);

  const {
    items: jobs,
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
    { page?: number; limit?: number; start?: number; search?: string; status?: string; provider?: string },
    BatchJobDoc
  >({
    fetchFn: async (params) => {
      const response = await getBatchJobs({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status,
        provider: params.provider,
      });

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

  const selectedStatus = filters.status || 'all';
  const selectedProvider = filters.provider || 'all';

  const columns = useMemo<ColumnDef<BatchJobDoc>[]>(
    () => [
      {
        accessorKey: 'agent',
        header: 'Agent',
        cell: ({ row }) => (
          <div className="font-body text-[13px] font-medium text-ink">
            {row.getValue('agent') || 'Unknown agent'}
          </div>
        ),
      },
      {
        accessorKey: 'provider',
        header: 'Provider',
        cell: ({ row }) => (
          <div className="font-body text-[13px] text-steel">{row.getValue('provider') || 'Not set'}</div>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => {
          const status = row.getValue('status') as string;
          const { variant, label } = getBatchJobStatusDot(status);
          return (
            <div className="flex items-center gap-2">
              <StatusDot variant={variant} />
              <span className="font-body text-[13px] text-steel">{label}</span>
            </div>
          );
        },
      },
      {
        id: 'submitted',
        header: () => <div className="text-right">Submitted</div>,
        cell: ({ row }) => (
          <div className="text-right font-mono text-[12px] tabular-nums text-steel">
            {row.original.submitted_at ? formatTimeAgo(row.original.submitted_at) : 'Not yet'}
          </div>
        ),
      },
      {
        id: 'completed',
        header: () => <div className="text-right">Completed</div>,
        cell: ({ row }) => (
          <div className="text-right font-mono text-[12px] tabular-nums text-steel">
            {row.original.completed_at ? formatTimeAgo(row.original.completed_at) : 'Not yet'}
          </div>
        ),
      },
      {
        id: 'estimated_cost',
        header: () => <div className="text-right">Est. cost</div>,
        cell: ({ row }) => (
          <div className="text-right font-mono text-[12px] tabular-nums text-steel">
            {formatEstimatedSavings(row.original.estimated_cost)}
          </div>
        ),
      },
    ],
    []
  );

  const table = useReactTable({
    data: jobs,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <PageFrame
      title="Batch jobs"
      filters={
        <FilterBar
          searchPlaceholder="Search batch jobs by agent"
          searchValue={search}
          onSearchChange={(value) => setSearch(value)}
          filters={[
            {
              label: 'Status',
              value: selectedStatus,
              options: STATUS_OPTIONS,
              onChange: (value) => setFilter('status', value),
            },
            {
              label: 'Provider',
              value: selectedProvider,
              options: PROVIDER_OPTIONS,
              onChange: (value) => setFilter('provider', value),
            },
          ]}
        />
      }
    >
      <div className="w-full rounded-lg border border-line bg-panel overflow-hidden">
        {initialLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : jobs.length === 0 ? (
          !!search || selectedStatus !== 'all' || selectedProvider !== 'all' ? (
            <EmptyState
              variant="no-results"
              icon={Layers}
              title="No batch jobs found"
              filterTerm={search}
              secondaryAction={{
                label: 'Clear filters',
                onClick: () => {
                  setSearch('');
                  setFilter('status', 'all');
                  setFilter('provider', 'all');
                },
              }}
            />
          ) : (
            <EmptyState
              variant="passive"
              icon={Layers}
              title="No batch jobs yet"
              description="Scheduled agents set to Batch execution mode will show up here once they run."
            />
          )
        ) : (
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <TableHead
                      key={header.id}
                      className={cn(
                        ['submitted', 'completed', 'estimated_cost'].includes(header.column.id) &&
                          'text-right'
                      )}
                    >
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
                  className="h-11 cursor-pointer hover:bg-paper-deep"
                  onClick={() => setSelectedJob(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        ['submitted', 'completed', 'estimated_cost'].includes(cell.column.id) &&
                          'text-right'
                      )}
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

      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />

      {!hasMore && jobs.length > 0 && (
        <div className="text-center py-4 text-sm text-steel">
          {total !== undefined ? `All ${total} batch jobs` : 'No more batch jobs to load'}
        </div>
      )}

      <BatchJobDetailDialog
        job={selectedJob}
        open={!!selectedJob}
        onOpenChange={(open) => {
          if (!open) setSelectedJob(null);
        }}
      />
    </PageFrame>
  );
}
