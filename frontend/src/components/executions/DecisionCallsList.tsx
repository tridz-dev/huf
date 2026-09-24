import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, ExternalLink, X } from 'lucide-react';
import { formatTimeAgo } from '@/utils/time';
import { listDecisionCalls } from '@/services/decisionApi';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/dashboard';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import { HelperText } from '@/components/ui/helper-text';

const RIGHT_ALIGNED_COLUMNS = new Set(['confidence', 'latency_ms', 'cost']);

/**
 * Map decision call status to badge variant
 */
function getStatusVariant(status?: string): 'default' | 'success' | 'destructive' | 'outline' {
  const normalized = status?.toLowerCase() || '';
  if (normalized === 'success') return 'success';
  if (normalized === 'failed' || normalized === 'timeout' || normalized === 'unavailable') return 'destructive';
  return 'outline';
}

/**
 * Truncate long text with ellipsis
 */
function TruncatedText({ text, maxChars = 40 }: { text?: string; maxChars?: number }) {
  if (!text) return '-';
  if (text.length <= maxChars) return text;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-help">{text.substring(0, maxChars)}...</span>
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  );
}

/**
 * Render origin link based on origin_type and related fields
 */
function OriginLink({ data }: { data: Record<string, unknown> }) {
  const originType = (data.origin_type as string) || '';
  const agentRun = (data.agent_run as string) || '';
  const flowRun = (data.flow_run as string) || '';
  const automation = (data.automation as string) || '';

  let href = '';
  let label = originType;

  if (originType === 'Agent' && agentRun) {
    href = `/executions/${agentRun}`;
    label = agentRun;
  } else if (originType === 'Flow' && flowRun) {
    href = `/flows/runs/${flowRun}`;
    label = flowRun;
  } else if (originType === 'Automation' && automation) {
    href = `/automations/${automation}`;
    label = automation;
  }

  if (!href) {
    return <span className="text-steel">{originType || '-'}</span>;
  }

  return (
    <a href={href} className="flex items-center gap-1.5 text-link hover:underline group">
      <span>{label}</span>
      <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
    </a>
  );
}

/**
 * DecisionCallsList — displays a paginated list of decision calls
 */
export function DecisionCallsList() {
  const navigate = useNavigate();
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ limit_start: 0, total: 0 });
  const [sorting, setSorting] = useState<SortingState>([]);

  // Filter state
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [showFilters, setShowFilters] = useState(false);

  // Load decision calls on mount and when pagination or filters change
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        // Reset pagination when filters change
        const hasFilters = Object.keys(filters).length > 0;
        const start = hasFilters ? 0 : pagination.limit_start;

        const response = await listDecisionCalls({
          filters: Object.keys(filters).length > 0 ? filters : undefined,
          limit_start: start,
          limit_page_length: 50,
          order_by: 'started_at desc',
        });
        setData(response.rows);
        setPagination({
          limit_start: start,
          total: response.total,
        });
      } catch (error) {
        console.error('Error loading decision calls:', error);
        setData([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [pagination.limit_start, filters]);

  // Define table columns
  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () => [
      {
        accessorKey: 'started_at',
        header: 'Time',
        cell: ({ row }) => (
          <div className="text-sm text-steel-soft">{formatTimeAgo(row.getValue('started_at') as string)}</div>
        ),
      },
      {
        accessorKey: 'surface',
        header: 'Surface',
        cell: ({ row }) => <div className="text-sm">{row.getValue('surface') || '-'}</div>,
      },
      {
        accessorKey: 'policy',
        header: 'Policy',
        cell: ({ row }) => <div className="text-sm">{row.getValue('policy') || '-'}</div>,
      },
      {
        accessorKey: 'mode',
        header: 'Mode',
        cell: ({ row }) => {
          const mode = row.getValue('mode') as string | undefined;
          return (
            <Badge variant={mode === 'Enforce' ? 'default' : 'outline'} className="text-xs">
              {mode || '-'}
            </Badge>
          );
        },
      },
      {
        accessorKey: 'answer_json',
        header: 'Answer',
        cell: ({ row }) => {
          const answer = row.getValue('answer_json') as string | undefined;
          return <TruncatedText text={answer} maxChars={30} />;
        },
      },
      {
        accessorKey: 'confidence',
        header: 'Confidence',
        cell: ({ row }) => {
          const conf = row.getValue('confidence') as number | undefined;
          if (conf === undefined || conf === null) return '-';
          return <div className="text-sm tabular-nums">{(conf * 100).toFixed(0)}%</div>;
        },
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => {
          const status = row.getValue('status') as string | undefined;
          return (
            <Badge variant={getStatusVariant(status)} className="text-xs">
              {status || '-'}
            </Badge>
          );
        },
      },
      {
        accessorKey: 'latency_ms',
        header: 'Latency',
        cell: ({ row }) => {
          const latency = row.getValue('latency_ms') as number | undefined;
          return <div className="text-sm tabular-nums text-right">{latency ? `${latency}ms` : '-'}</div>;
        },
      },
      {
        accessorKey: 'cost',
        header: 'Cost',
        cell: ({ row }) => {
          const cost = row.getValue('cost') as number | undefined;
          return (
            <div className="text-sm tabular-nums text-right">
              ${cost ? cost.toFixed(6) : '0.00'}
            </div>
          );
        },
      },
      {
        accessorKey: 'origin',
        header: 'Origin',
        cell: ({ row }) => <OriginLink data={row.original} />,
      },
    ],
    []
  );

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    state: {
      sorting,
    },
    onSortingChange: setSorting,
  });

  if (loading && data.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <EmptyState
        variant="passive"
        title="No decision calls"
        description="No decisions have been recorded yet."
      />
    );
  }

  const pageSize = 50;
  const currentPage = Math.floor(pagination.limit_start / pageSize) + 1;
  const totalPages = Math.ceil(pagination.total / pageSize);
  const hasNextPage = currentPage < totalPages;
  const hasPrevPage = currentPage > 1;

  const hasActiveFilters = Object.keys(filters).length > 0;

  return (
    <div className="w-full space-y-4">
      {/* Filters Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-steel">Filters</h3>
          {hasActiveFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setFilters({});
                setPagination({ limit_start: 0, total: pagination.total });
              }}
              className="text-xs"
            >
              <X className="h-3 w-3 mr-1" />
              Clear filters
            </Button>
          )}
        </div>

        {showFilters && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 p-3 bg-paper rounded-lg border border-line">
            {/* Surface filter */}
            <div>
              <label className="text-xs text-steel-soft mb-1 block">Surface</label>
              <Input
                placeholder="e.g. Tool Selection"
                value={(filters.surface as string) || ''}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    surface: e.target.value || undefined,
                  }))
                }
                className="h-8 text-xs"
              />
            </div>

            {/* Policy filter */}
            <div>
              <label className="text-xs text-steel-soft mb-1 block">Policy</label>
              <Input
                placeholder="Policy name"
                value={(filters.policy as string) || ''}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    policy: e.target.value || undefined,
                  }))
                }
                className="h-8 text-xs"
              />
            </div>

            {/* Policy Version filter */}
            <div>
              <label className="text-xs text-steel-soft mb-1 block">Version</label>
              <Input
                placeholder="Version"
                value={(filters.policy_version as string) || ''}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    policy_version: e.target.value || undefined,
                  }))
                }
                className="h-8 text-xs"
              />
            </div>

            {/* Mode filter */}
            <div>
              <label className="text-xs text-steel-soft mb-1 block">Mode</label>
              <Select
                value={(filters.mode as string) || ''}
                onValueChange={(value) =>
                  setFilters((prev) => ({
                    ...prev,
                    mode: value || undefined,
                  }))
                }
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="All modes" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All modes</SelectItem>
                  <SelectItem value="Off">Off</SelectItem>
                  <SelectItem value="Shadow">Shadow</SelectItem>
                  <SelectItem value="Advise">Advise</SelectItem>
                  <SelectItem value="Enforce">Enforce</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Status filter */}
            <div>
              <label className="text-xs text-steel-soft mb-1 block">Status</label>
              <Select
                value={(filters.status as string) || ''}
                onValueChange={(value) =>
                  setFilters((prev) => ({
                    ...prev,
                    status: value || undefined,
                  }))
                }
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All statuses</SelectItem>
                  <SelectItem value="success">Success</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                  <SelectItem value="timeout">Timeout</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Agent filter */}
            <div>
              <label className="text-xs text-steel-soft mb-1 block">Agent</label>
              <Input
                placeholder="Agent name"
                value={(filters.agent as string) || ''}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    agent: e.target.value || undefined,
                  }))
                }
                className="h-8 text-xs"
              />
            </div>
          </div>
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowFilters(!showFilters)}
          className="text-xs"
        >
          {showFilters ? 'Hide filters' : 'Show filters'}
        </Button>
      </div>

      <div className="rounded-lg border border-line bg-panel overflow-hidden">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    className={cn(RIGHT_ALIGNED_COLUMNS.has(header.column.id) && 'text-right')}
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
                key={row.original.name as string}
                className="h-11 cursor-pointer hover:bg-paper-deep"
                onClick={() => navigate(`/executions/decisions/${row.original.name as string}`)}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    className={cn(RIGHT_ALIGNED_COLUMNS.has(cell.column.id) && 'text-right')}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <HelperText>
        Showing {data.length} of {pagination.total} decision calls
      </HelperText>

      {/* Pagination controls */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-steel">
          Page {currentPage} of {totalPages || 1}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!hasPrevPage}
            onClick={() => {
              setPagination((prev) => ({
                ...prev,
                limit_start: Math.max(0, prev.limit_start - pageSize),
              }));
            }}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasNextPage}
            onClick={() => {
              setPagination((prev) => ({
                ...prev,
                limit_start: prev.limit_start + pageSize,
              }));
            }}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
