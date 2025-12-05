import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, ArrowUpDown, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { AgentRunDoc } from '@/services/agentRunApi';
import { getAgentRuns } from '@/services/agentRunApi';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { calculateDuration, formatTimeAgo } from '@/utils/time';
import { getAgentRunStatusVariant } from '@/utils/status';
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

interface AgentRunDetail extends AgentRunDoc {
  prompt?: string;
  response?: string;
  provider?: string;
  model?: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cost?: number | null;
}

async function fetchAgentRunDetail(name: string): Promise<AgentRunDetail | null> {
  try {
    const doc = await db.getDoc(doctype['Agent Run'], name);
    return doc as AgentRunDetail;
  } catch (error) {
    handleFrappeError(error, `Error fetching agent run ${name}`);
    return null;
  }
}

export function AgentRunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<AgentRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [childRuns, setChildRuns] = useState<AgentRunDoc[]>([]);
  const [loadingChildRuns, setLoadingChildRuns] = useState(false);
  const [sorting, setSorting] = useState<SortingState>([]);

  useEffect(() => {
    if (!runId) {
      setLoading(false);
      return;
    }

    (async () => {
      setLoading(true);
      const data = await fetchAgentRunDetail(runId);
      setRun(data);
      setLoading(false);
    })();
  }, [runId]);

  // Fetch child runs when run is loaded
  useEffect(() => {
    if (!runId || !run) {
      return;
    }

    (async () => {
      setLoadingChildRuns(true);
      try {
        const response = await getAgentRuns({
          page: 1,
          limit: 1000,
          start: 0,
          filters: [['parent_run', '=', runId]],
        });

        if (Array.isArray(response)) {
          setChildRuns(response);
        } else {
          setChildRuns(response.items);
        }
      } catch (error) {
        console.error('Error fetching child runs:', error);
        setChildRuns([]);
      } finally {
        setLoadingChildRuns(false);
      }
    })();
  }, [runId, run]);

  // Define table columns for child runs (similar to Executions page)
  // MUST be called before any early returns to follow Rules of Hooks
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

  const table = useReactTable({
    data: childRuns,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: {
      sorting,
    },
  });

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading run details...</span>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="h-full overflow-auto">
        <div className="p-6 max-w-4xl mx-auto space-y-4">
          <Button
            variant="ghost"
            className="px-0"
            onClick={() => navigate('/executions')}
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Executions
          </Button>
          <Card>
            <CardHeader>
              <CardTitle>Run not found</CardTitle>
              <CardDescription>This agent run could not be loaded.</CardDescription>
            </CardHeader>
          </Card>
        </div>
      </div>
    );
  }

  const status = run.status || 'Unknown';
  const duration = calculateDuration(run.start_time ?? null, run.end_time ?? null);
  const startedAt = run.start_time ? formatTimeAgo(run.start_time) : 'Not available';

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-5xl mx-auto">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              onClick={() => navigate('/executions')}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Executions
            </Button>
          </div>
        </div>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-3">
                Agent Run
                <Badge variant={getAgentRunStatusVariant(run.status)}>{status}</Badge>
              </CardTitle>
              <CardDescription className="mt-1">
                {run.agent || 'Unknown Agent'} • Run ID: {run.name}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid gap-8 md:grid-cols-2">
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-muted-foreground">Overview</h3>
                <div className="space-y-1 text-sm">
                  <Link to={`/agents/${run.agent}`} className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Agent</span>
                    <span className="font-medium truncate">{run.agent || 'Unknown'}</span>
                  </Link>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Provider</span>
                    <span className="font-medium truncate">{run.provider || 'Unknown'}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Model</span>
                    <span className="font-medium truncate">{run.model || 'Unknown'}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Status</span>
                    <span className="font-medium">{status}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Started</span>
                    <span className="font-medium">{startedAt}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Duration</span>
                    <span className="font-medium">{duration}</span>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-muted-foreground">Tokens & Cost</h3>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Input Tokens</span>
                    <span className="font-medium">
                      {typeof run.input_tokens === 'number' ? run.input_tokens : 'Not available'}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Output Tokens</span>
                    <span className="font-medium">
                      {typeof run.output_tokens === 'number' ? run.output_tokens : 'Not available'}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Total Tokens</span>
                    <span className="font-medium">
                      {typeof run.input_tokens === 'number' || typeof run.output_tokens === 'number'
                        ? (run.input_tokens || 0) + (run.output_tokens || 0)
                        : 'Not available'}
                    </span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Cost</span>
                    <span className="font-medium">
                      {typeof run.cost === 'number' ? `$${run.cost.toFixed(6)}` : 'Not available'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Prompt</CardTitle>
              <CardDescription>
                Full prompt sent to the model for this run.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="rounded-md bg-muted p-3 text-sm whitespace-pre-wrap break-words max-h-[320px] overflow-auto">
                {run.prompt || 'No prompt recorded.'}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Response</CardTitle>
              <CardDescription>
                Final response returned by the model.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="rounded-md bg-muted p-3 text-sm whitespace-pre-wrap break-words max-h-[320px] overflow-auto">
                {run.response || 'No response recorded.'}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Agent Orchestration Table */}
        {childRuns.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Agent Orchestration</CardTitle>
              <CardDescription>
                Child agent runs executed as part of this orchestration.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loadingChildRuns ? (
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
                            <div className="text-muted-foreground">No child runs found.</div>
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}


