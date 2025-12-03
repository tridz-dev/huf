import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { AgentRunDoc } from '@/services/agentRunApi';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { calculateDuration, formatTimeAgo } from '@/utils/time';
import { getAgentRunStatusVariant } from '@/utils/status';

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
      </div>
    </div>
  );
}


