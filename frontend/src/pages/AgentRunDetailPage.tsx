import { useEffect, useState, useMemo, type ReactNode } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowUpDown, Loader2, AlertTriangle, Copy, Check } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { PageFrame } from '@/layouts/PageFrame';
import { cn } from '@/lib/utils';
import type { AgentRunDoc } from '@/services/agentRunApi';
import { getAgentRuns } from '@/services/agentRunApi';
import { checkCacheableModels } from '@/services/agentApi';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { calculateDuration, formatTimeAgo } from '@/utils/time';
import { getAgentRunStatusVariant } from '@/utils/status';
import { getRunContextMetrics } from '@/services/runContextMetricsApi';
import type { RunContextMetricsResponse } from '@/types/runContextMetrics.types';
import { ContextBar } from '@/components/ui/context-bar';
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

/** One row of the Overview / Tokens & Cost definition list. */
function DefinitionRow({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex h-[26px] items-center justify-between gap-4">
      <span className="text-[13px] text-steel shrink-0">{label}</span>
      <span
        className={cn(
          'text-[13px] tabular-nums truncate text-right text-ink',
          mono && 'font-mono'
        )}
      >
        {value}
      </span>
    </div>
  );
}

/** A labeled column of DefinitionRows, headed by a mono uppercase eyebrow. */
function DefinitionColumn({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-steel pb-1.5">{heading}</div>
      <div className="divide-y divide-line">{children}</div>
    </div>
  );
}

/** One field in the Context panel's four-column stat row: 11px label over a 13px value. */
function ContextStat({
  label,
  value,
  capitalize,
}: {
  label: string;
  value: ReactNode;
  capitalize?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-steel truncate">{label}</div>
      <div className={cn('text-[13px] tabular-nums text-ink truncate', capitalize && 'capitalize')}>
        {value}
      </div>
    </div>
  );
}

/** Prompt/Response panel: title + copy button, content in a mono box. */
function CopyableTextPanel({
  title,
  content,
  emptyText,
}: {
  title: string;
  content?: string | null;
  emptyText: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
    }
  };

  return (
    <div className="rounded-lg border border-line bg-panel p-4">
      <div className="flex items-center justify-between gap-2 pb-2">
        <h3 className="text-[13px] font-[590] text-ink">{title}</h3>
        <button
          type="button"
          onClick={handleCopy}
          disabled={!content}
          aria-label={`Copy ${title.toLowerCase()}`}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-steel transition-colors hover:bg-paper-deep hover:text-ink disabled:pointer-events-none disabled:opacity-40"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="max-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-paper-deep p-3 font-mono text-xs leading-[1.6] text-ink">
        {content || emptyText}
      </div>
    </div>
  );
}

interface AgentRunDetail extends AgentRunDoc {
  prompt?: string;
  response?: string;
  provider?: string;
  model?: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_tokens?: number | null;
  cost?: number | null;
  cost_source?: string | null;
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

export { AgentRunDetailPage };
export default AgentRunDetailPage;

function AgentRunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<AgentRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [childRuns, setChildRuns] = useState<AgentRunDoc[]>([]);
  const [loadingChildRuns, setLoadingChildRuns] = useState(false);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [isSilentDegradation, setIsSilentDegradation] = useState(false);
  const [contextMetrics, setContextMetrics] = useState<RunContextMetricsResponse | null>(null);

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

    (async () => {
      const metrics = await getRunContextMetrics(runId);
      setContextMetrics(metrics);
    })();
  }, [runId]);

  // Check for silent degradation (caching enabled on agent but unsupported by model)
  useEffect(() => {
    if (!run || !run.agent || !run.provider || !run.model) {
      setIsSilentDegradation(false);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const agentDoc = await db.getDoc(doctype.Agent, run.agent);
        if (agentDoc && agentDoc.enable_prompt_caching) {
          const cacheCheck = await checkCacheableModels(run.provider, run.model);
          if (!cancelled && !cacheCheck.supported) {
            setIsSilentDegradation(true);
            return;
          }
        }
        if (!cancelled) {
          setIsSilentDegradation(false);
        }
      } catch {
        if (!cancelled) {
          setIsSilentDegradation(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [run]);

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
          <div className="font-mono text-sm text-steel-soft">{row.getValue('name')}</div>
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
        accessorKey: 'cached_tokens',
        header: ({ column }) => {
          return (
            <Button
              variant="ghost"
              onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
              className="h-8 px-2"
            >
              Cached tokens
              <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
          );
        },
        cell: ({ row }) => {
          const cached = row.original.cached_tokens;
          return (
            <div className="font-mono text-sm text-steel">
              {typeof cached === 'number' ? cached.toLocaleString() : '0'}
            </div>
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
          return <div className="text-sm text-steel">{timeAgo}</div>;
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
        <div className="flex items-center gap-2 text-steel">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading run details...</span>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <PageFrame className="mx-auto w-full max-w-4xl">
        <Card>
          <CardHeader>
            <CardTitle>Run not found</CardTitle>
            <CardDescription>This agent run could not be loaded.</CardDescription>
          </CardHeader>
        </Card>
      </PageFrame>
    );
  }

  const status = run.status || 'Unknown';
  const duration = calculateDuration(run.start_time ?? null, run.end_time ?? null);
  const startedAt = run.start_time ? formatTimeAgo(run.start_time) : 'Not available';

  return (
    <PageFrame className="mx-auto w-full max-w-5xl">
      <div className="space-y-6">
        {isSilentDegradation && (
          <Alert className="border-warning/50 bg-warning/10 text-warning">
            <AlertTriangle className="h-4 w-4 text-warning" />
            <AlertTitle className="font-semibold text-sm">Silent Degradation Warning: Prompt Caching Skipped</AlertTitle>
            <AlertDescription className="text-xs mt-1">
              Prompt caching was enabled for agent <strong>{run.agent}</strong>, but model <strong>{run.model || 'unknown'}</strong> from provider <strong>{run.provider || 'unknown'}</strong> does not support prompt caching. Caching was silently skipped during execution.
            </AlertDescription>
          </Alert>
        )}

        <div className="rounded-lg border border-line bg-panel p-5">
          <div className="flex flex-wrap items-center gap-3 pb-4">
            <h2 className="text-[17px] font-[600] text-ink">Agent run</h2>
            <Badge variant={getAgentRunStatusVariant(run.status)}>{status}</Badge>
            <span className="text-[13px] text-steel">{run.agent || 'Unknown agent'}</span>
          </div>

          <div className="grid gap-x-10 gap-y-4 md:grid-cols-2">
            <DefinitionColumn heading="Overview">
              <DefinitionRow
                label="Agent"
                value={
                  <Link to={`/agents/${run.agent}`} className="hover:text-signal">
                    {run.agent || 'Unknown'}
                  </Link>
                }
              />
              <DefinitionRow label="Provider" value={run.provider || 'Unknown'} />
              <DefinitionRow label="Model" value={run.model || 'Unknown'} mono />
              <DefinitionRow label="Started" value={startedAt} />
              <DefinitionRow label="Duration" value={duration} />
            </DefinitionColumn>

            <DefinitionColumn heading="Tokens & Cost">
              <DefinitionRow
                label="Input"
                value={typeof run.input_tokens === 'number' ? run.input_tokens.toLocaleString() : 'Not available'}
              />
              <DefinitionRow
                label="Output"
                value={typeof run.output_tokens === 'number' ? run.output_tokens.toLocaleString() : 'Not available'}
              />
              <DefinitionRow
                label="Cached"
                value={typeof run.cached_tokens === 'number' ? run.cached_tokens.toLocaleString() : 'Not available'}
              />
              <DefinitionRow
                label="Cost"
                value={typeof run.cost === 'number' ? `$${run.cost.toFixed(6)}` : 'Not available'}
              />
              <DefinitionRow label="Cost source" value={run.cost_source || 'Not available'} />
            </DefinitionColumn>
          </div>
        </div>

        {contextMetrics?.segment_tokens && (
          <Card>
            <CardHeader>
              <CardTitle>Context</CardTitle>
              <CardDescription>
                What filled the context window this turn, and whether caching paid off.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ContextBar
                segments={contextMetrics.segment_tokens}
                total={contextMetrics.context_window}
                showLegend
                cacheState={
                  typeof contextMetrics.metrics.cache_read_share === 'number'
                    ? {
                        cacheRead: run.cached_tokens || 0,
                        cacheWrite: 0,
                        uncached: Math.max(
                          (contextMetrics.total_tokens || run.input_tokens || 0) - (run.cached_tokens || 0),
                          0
                        ),
                      }
                    : undefined
                }
              />
              <div className="grid grid-cols-4 gap-x-4 gap-y-2 border-t border-line pt-3">
                <ContextStat label="Prefix stability" value={contextMetrics.metrics.prefix_stability} capitalize />
                <ContextStat
                  label="Effective multiplier"
                  value={
                    typeof contextMetrics.metrics.effective_input_multiplier === 'number'
                      ? `${contextMetrics.metrics.effective_input_multiplier.toFixed(2)}x`
                      : 'Unavailable'
                  }
                />
                <ContextStat
                  label="Counterfactual saving"
                  value={
                    typeof contextMetrics.metrics.counterfactual_savings === 'number'
                      ? `$${contextMetrics.metrics.counterfactual_savings.toFixed(6)}`
                      : 'Unavailable'
                  }
                />
                <ContextStat
                  label="Wasted writes"
                  value={
                    typeof contextMetrics.metrics.wasted_writes_tokens === 'number'
                      ? contextMetrics.metrics.wasted_writes_tokens.toLocaleString()
                      : 'Not yet tracked'
                  }
                />
              </div>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <CopyableTextPanel title="Prompt" content={run.prompt} emptyText="No prompt recorded." />
          <CopyableTextPanel title="Response" content={run.response} emptyText="No response recorded." />
        </div>

        {/* Agent Orchestration Table */}
        {childRuns.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Agent orchestration</CardTitle>
              <CardDescription>
                Child agent runs executed as part of this orchestration.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loadingChildRuns ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
                </div>
              ) : (
                <div className="overflow-hidden rounded-lg border">
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
                            className="cursor-pointer hover:bg-paper-deep"
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
                            <div className="font-body text-steel-soft">No child runs found.</div>
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
    </PageFrame>
  );
}
