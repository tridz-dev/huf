import { useEffect, useState, type ReactNode } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Loader2, AlertTriangle, ExternalLink } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { PageFrame } from '@/layouts/PageFrame';
import { cn } from '@/lib/utils';
import { getDecisionCall } from '@/services/decisionApi';
import { handleFrappeError } from '@/lib/frappe-error';
import { formatTimeAgo } from '@/utils/time';
import { usePermissions } from '@/contexts/PermissionsContext';

/** One row of the definition list. */
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
      <div className="font-mono text-[10px] uppercase tracking-widest text-steel pb-1.5">
        {heading}
      </div>
      <div className="divide-y divide-line">{children}</div>
    </div>
  );
}

/**
 * Map status to a color variant
 */
function getStatusVariant(status?: string): 'default' | 'success' | 'destructive' | 'outline' {
  const normalized = status?.toLowerCase() || '';
  if (normalized === 'success') return 'success';
  if (normalized === 'failed' || normalized === 'timeout' || normalized === 'unavailable') return 'destructive';
  return 'outline';
}

/**
 * Render origin link
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
    return <span>{originType || '-'}</span>;
  }

  return (
    <a href={href} className="flex items-center gap-1.5 text-link hover:underline group">
      <span>{label}</span>
      <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
    </a>
  );
}

/**
 * Format probabilities JSON object into human-readable text
 */
function formatProbabilities(probs?: Record<string, number> | string): string {
  if (!probs) return '-';
  try {
    const obj = typeof probs === 'string' ? JSON.parse(probs) : probs;
    return Object.entries(obj)
      .map(([k, v]) => {
        const vNum = typeof v === 'number' ? v : Number(v);
        return `${k}: ${(vNum * 100).toFixed(1)}%`;
      })
      .join(', ');
  } catch {
    return String(probs);
  }
}

/**
 * Format deployment chain
 */
function formatDeploymentChain(chain?: string[]): string {
  if (!chain || !Array.isArray(chain) || chain.length === 0) return '-';
  return chain.join(' → ');
}

interface DecisionCallDetail extends Record<string, unknown> {
  name?: string;
  status?: string;
  surface?: string;
  policy?: string;
  policy_version?: string;
  mode?: string;
  origin_type?: string;
  started_at?: string;
  ended_at?: string;
  latency_ms?: number;
  decision_model?: string;
  resolved_model?: string;
  resolved_model_version?: string;
  resolved_deployment?: string;
  resolved_provider?: string;
  resolved_provider_model_id?: string;
  backend_adapter?: string;
  deployment_fallback_chain?: string[];
  deployment_fallback_count?: number;
  answer_json?: string;
  confidence?: number;
  probabilities_json?: string;
  gate_result?: string;
  fallback_action?: string;
  input_tokens?: number;
  output_tokens?: number;
  cost?: number;
  cost_source?: string;
  agent_run?: string;
  flow_run?: string;
  automation?: string;
  state_snapshot?: string;
  error_code?: string;
  error_message?: string;
}

export default function DecisionCallDetail() {
  const { name } = useParams<{ name: string }>();
  const { hasCapability } = usePermissions();
  const [data, setData] = useState<DecisionCallDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = hasCapability('decision.admin');

  useEffect(() => {
    if (!name) {
      setError('No decision call ID provided');
      setLoading(false);
      return;
    }

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const callData = await getDecisionCall(name);
        setData(callData as DecisionCallDetail);
      } catch (err) {
        handleFrappeError(err, `Error fetching decision call ${name}`);
        // Use the actual error message instead of a generic fallback
        const message = err instanceof Error ? err.message : `Failed to load decision call ${name}`;
        setError(message);
      } finally {
        setLoading(false);
      }
    })();
  }, [name]);

  if (loading) {
    return (
      <PageFrame title="Decision Call">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
        </div>
      </PageFrame>
    );
  }

  if (error || !data) {
    return (
      <PageFrame title="Decision Call">
        <Alert variant="destructive" className="max-w-2xl">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error || 'Decision call not found'}</AlertDescription>
        </Alert>
      </PageFrame>
    );
  }

  return (
    <PageFrame
      title="Decision Call"
      meta={data.name}
    >
      <div className="max-w-4xl space-y-6">
        {/* Status and basic info card */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between">
              <CardTitle>Overview</CardTitle>
              <Badge variant={getStatusVariant(data.status as string)}>
                {data.status || 'Unknown'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <DefinitionColumn heading="TIMING">
              <DefinitionRow
                label="Started"
                value={data.started_at ? formatTimeAgo(data.started_at as string) : '-'}
              />
              <DefinitionRow
                label="Latency"
                value={
                  data.latency_ms
                    ? `${data.latency_ms}ms`
                    : '-'
                }
              />
            </DefinitionColumn>

            <DefinitionColumn heading="ORIGIN">
              <DefinitionRow label="Type" value={data.origin_type || '-'} />
              <DefinitionRow label="Link" value={<OriginLink data={data} />} />
            </DefinitionColumn>

            <DefinitionColumn heading="POLICY">
              <DefinitionRow
                label="Policy"
                value={
                  data.policy ? (
                    <Link to={`/decisions/${data.policy}`} className="text-link hover:underline">
                      {data.policy}
                    </Link>
                  ) : (
                    '-'
                  )
                }
              />
              <DefinitionRow label="Version" value={data.policy_version || '-'} />
            </DefinitionColumn>

            <DefinitionColumn heading="EXECUTION">
              <DefinitionRow label="Surface" value={data.surface || '-'} />
              <DefinitionRow label="Mode" value={data.mode || '-'} />
            </DefinitionColumn>
          </CardContent>
        </Card>

        {/* Answer and confidence card */}
        <Card>
          <CardHeader>
            <CardTitle>Answer</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <DefinitionColumn heading="RESULT">
              <DefinitionRow
                label="Answer"
                value={data.answer_json ? (
                  <code className="text-xs text-mono">{String(data.answer_json).substring(0, 60)}</code>
                ) : (
                  '-'
                )}
              />
              <DefinitionRow
                label="Confidence"
                value={
                  data.confidence !== undefined
                    ? `${(Number(data.confidence) * 100).toFixed(1)}%`
                    : '-'
                }
              />
            </DefinitionColumn>

            <DefinitionColumn heading="PROBABILITIES">
              <DefinitionRow
                label="Distribution"
                value={<div className="text-xs">{formatProbabilities(data.probabilities_json as any)}</div>}
              />
            </DefinitionColumn>

            <DefinitionColumn heading="GATE">
              <DefinitionRow label="Gate Result" value={data.gate_result || '-'} />
              <DefinitionRow label="Fallback" value={data.fallback_action || '-'} />
            </DefinitionColumn>
          </CardContent>
        </Card>

        {/* Model and deployment card */}
        <Card>
          <CardHeader>
            <CardTitle>Model & Deployment</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <DefinitionColumn heading="RESOLUTION">
              <DefinitionRow label="Decision Model" value={data.decision_model || '-'} />
              <DefinitionRow label="Resolved Model" value={data.resolved_model || '-'} />
              <DefinitionRow
                label="Model Version"
                value={data.resolved_model_version || '-'}
              />
            </DefinitionColumn>

            <DefinitionColumn heading="DEPLOYMENT">
              <DefinitionRow label="Deployment" value={data.resolved_deployment || '-'} />
              <DefinitionRow label="Provider" value={data.resolved_provider || '-'} />
              <DefinitionRow
                label="Provider Model ID"
                value={data.resolved_provider_model_id || '-'}
                mono
              />
            </DefinitionColumn>

            <DefinitionColumn heading="FAILOVER">
              <DefinitionRow
                label="Fallback Count"
                value={data.deployment_fallback_count || '0'}
              />
              <DefinitionRow
                label="Chain"
                value={
                  <div className="text-xs">
                    {formatDeploymentChain(data.deployment_fallback_chain as string[])}
                  </div>
                }
              />
            </DefinitionColumn>

            <DefinitionColumn heading="BACKEND">
              <DefinitionRow label="Adapter" value={data.backend_adapter || '-'} />
            </DefinitionColumn>
          </CardContent>
        </Card>

        {/* Usage and cost card */}
        <Card>
          <CardHeader>
            <CardTitle>Usage & Cost</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <DefinitionColumn heading="TOKENS">
              <DefinitionRow label="Input Tokens" value={data.input_tokens || '0'} />
              <DefinitionRow label="Output Tokens" value={data.output_tokens || '0'} />
            </DefinitionColumn>

            <DefinitionColumn heading="COST">
              <DefinitionRow
                label="Total"
                value={`$${Number(data.cost || 0).toFixed(6)}`}
                mono
              />
              <DefinitionRow label="Source" value={data.cost_source || '-'} />
            </DefinitionColumn>
          </CardContent>
        </Card>

        {/* Error information card (if present) */}
        {(data.error_code || data.error_message) && (
          <Card>
            <CardHeader>
              <CardTitle className="text-destructive">Error</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-6">
              <DefinitionColumn heading="ERROR">
                <DefinitionRow label="Code" value={data.error_code || '-'} />
                <DefinitionRow label="Message" value={data.error_message || '-'} />
              </DefinitionColumn>
            </CardContent>
          </Card>
        )}

        {/* Admin-only: raw state and snapshots */}
        {isAdmin && (
          <Card className="border-warning bg-warning/5">
            <CardHeader>
              <CardTitle className="text-sm">Advanced (Admin Only)</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-6">
              {data.state_snapshot && (
                <div>
                  <div className="text-xs font-mono uppercase tracking-widest text-steel pb-2">
                    STATE SNAPSHOT
                  </div>
                  <pre className="bg-paper-deep rounded p-3 text-xs overflow-auto max-h-40 border border-line">
                    {typeof data.state_snapshot === 'string'
                      ? data.state_snapshot
                      : JSON.stringify(data.state_snapshot, null, 2)}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </PageFrame>
  );
}
