import { useState, useEffect } from 'react';
import { Loader2, Info } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { listDecisionCalls } from '@/services/decisionApi';
import type { DecisionCallListResponse } from '@/services/decisionApi';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface RunDecisionsSectionProps {
  agentRunName?: string;
  flowRunName?: string;
  title?: string;
  description?: string;
}

/**
 * RunDecisionsSection displays decision calls for a run (agent run or flow run).
 * Shows a table of calls with links to detail pages, and totals for tokens and cost.
 * Reusable by both AgentRunDetailPage and FlowRunViewer.
 */
export function RunDecisionsSection({
  agentRunName,
  flowRunName,
  title = 'Decisions',
  description = 'Decision calls executed during this run.',
}: RunDecisionsSectionProps) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<DecisionCallListResponse | null>(null);

  useEffect(() => {
    async function fetchCalls() {
      if (!agentRunName && !flowRunName) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const filters: Record<string, unknown> = {};
        if (agentRunName) filters.agent_run = agentRunName;
        if (flowRunName) filters.flow_run = flowRunName;

        const response = await listDecisionCalls({
          filters,
          limit_page_length: 100, // reasonable page size for a run's calls
        });
        setData(response);
      } catch (error) {
        console.error('Error fetching decision calls:', error);
        setData({ rows: [], total: 0, limit_start: 0, limit_page_length: 100 });
      } finally {
        setLoading(false);
      }
    }

    fetchCalls();
  }, [agentRunName, flowRunName]);

  // If no run specified or no calls, don't render
  if (!agentRunName && !flowRunName) {
    return null;
  }

  // Calculate totals
  type RunDecisionTotals = { callCount: number; inputTokens: number; outputTokens: number; cost: number };
  const totals: RunDecisionTotals = data?.rows.reduce<RunDecisionTotals>(
    (acc, row) => {
      const call = row as Record<string, unknown>;
      return {
        callCount: acc.callCount + 1,
        inputTokens: acc.inputTokens + ((call.decision_input_tokens as number) || 0),
        outputTokens: acc.outputTokens + ((call.decision_output_tokens as number) || 0),
        cost: acc.cost + ((call.decision_cost as number) || 0),
      };
    },
    { callCount: 0, inputTokens: 0, outputTokens: 0, cost: 0 }
  ) || { callCount: 0, inputTokens: 0, outputTokens: 0, cost: 0 };

  // No decisions recorded
  if (!loading && (!data?.rows || data.rows.length === 0)) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>{title}</CardTitle>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-4 w-4 text-steel-soft hover:text-ink cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-xs">
                <p>Decision calls executed during this run. Shows policy decisions made and their usage metrics.</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>

      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : data?.rows && data.rows.length > 0 ? (
          <div className="space-y-4">
            {/* Totals row */}
            <div className="grid grid-cols-4 gap-4 p-4 rounded-lg bg-paper-deep border border-line">
              <div>
                <div className="text-[11px] text-steel uppercase tracking-widest font-mono">Calls</div>
                <div className="text-[13px] font-[590] text-ink">{totals.callCount}</div>
              </div>
              <div>
                <div className="text-[11px] text-steel uppercase tracking-widest font-mono">Input tokens</div>
                <div className="text-[13px] font-mono tabular-nums text-ink">{totals.inputTokens.toLocaleString()}</div>
              </div>
              <div>
                <div className="text-[11px] text-steel uppercase tracking-widest font-mono">Output tokens</div>
                <div className="text-[13px] font-mono tabular-nums text-ink">
                  {totals.outputTokens.toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-steel uppercase tracking-widest font-mono">Cost</div>
                <div className="text-[13px] font-mono tabular-nums text-ink">
                  ${totals.cost.toFixed(6)}
                </div>
              </div>
            </div>

            {/* Calls table */}
            <div className="overflow-hidden rounded-lg border border-line">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-mono text-[10px] uppercase tracking-widest">Call ID</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase tracking-widest">Policy</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase tracking-widest">Model</TableHead>
                    <TableHead className="text-right font-mono text-[10px] uppercase tracking-widest">
                      Input tokens
                    </TableHead>
                    <TableHead className="text-right font-mono text-[10px] uppercase tracking-widest">
                      Output tokens
                    </TableHead>
                    <TableHead className="text-right font-mono text-[10px] uppercase tracking-widest">Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.rows.map((row) => {
                    const call = row as Record<string, unknown>;
                    const callName = call.name as string;
                    const policy = call.policy as string;
                    const decisionModel = call.decision_model as string;
                    const inputTokens = (call.decision_input_tokens as number) || 0;
                    const outputTokens = (call.decision_output_tokens as number) || 0;
                    const cost = (call.decision_cost as number) || 0;

                    return (
                      <TableRow
                        key={callName}
                        className="h-10 cursor-pointer hover:bg-paper-deep"
                        onClick={() => navigate(`/executions/decisions/${callName}`)}
                      >
                        <TableCell className="font-mono text-[12px] text-steel">{callName}</TableCell>
                        <TableCell className="text-[13px] text-ink">{policy || 'N/A'}</TableCell>
                        <TableCell className="font-mono text-[12px] text-steel">{decisionModel || 'N/A'}</TableCell>
                        <TableCell className="text-right font-mono text-[12px] tabular-nums text-steel">
                          {inputTokens.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right font-mono text-[12px] tabular-nums text-steel">
                          {outputTokens.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right font-mono text-[12px] tabular-nums text-steel">
                          ${cost.toFixed(6)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            {data.total > data.rows.length && (
              <p className="text-[12px] text-steel-soft text-center py-2">
                Showing {data.rows.length} of {data.total} decision calls
              </p>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-steel-soft">
            <p className="text-[13px]">No decisions recorded for this run.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
