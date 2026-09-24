import { useState, useEffect, useRef, type ReactNode } from 'react';
import { Loader2, AlertCircle, ArrowUpRight, ChevronDown, Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { StatusDot } from '@/components/dashboard';
import {
  listDecisionModels,
  runDecision,
  type DecisionModel,
  type RunDecisionResult,
  type DecisionAnswer,
} from '@/services/decisionApi';
import {
  QuestionBuilder,
  newPolicyDefinition,
  type PolicyDefinition,
} from '@/components/decision/QuestionBuilder';
import { usePermissions } from '@/contexts/PermissionsContext';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { cn } from '@/lib/utils';
import { ConfigStripCell, flushTriggerClass } from './ConfigStrip';

const AUTO_DEPLOYMENT = 'auto';

/**
 * Plain-language description for a `huf.ai.decision.errors.DecisionErrorCode` value, so a
 * failed run says what actually happened instead of a bare status badge. Descriptions state
 * only what the backend guarantees about each code (see errors.py) -- no invented specifics
 * about the caller's own data.
 */
function describeDecisionErrorCode(code: string): string {
  switch (code) {
    case 'DECISION_PROVIDER_UNAVAILABLE':
      return 'The provider could not be reached (no working deployment, or the connection failed).';
    case 'DECISION_AUTHENTICATION_FAILED':
      return "The provider rejected the request's credentials.";
    case 'DECISION_TIMEOUT':
      return 'The provider did not respond within the latency budget.';
    case 'DECISION_RATE_LIMITED':
      return 'The provider rate-limited this request.';
    case 'DECISION_INVALID_RESPONSE':
      return "The provider's response could not be parsed into a decision answer.";
    case 'DECISION_UNSUPPORTED_CAPABILITY':
      return "This deployment doesn't support a capability the policy needs (e.g. probabilities or confidence).";
    case 'DECISION_POLICY_INVALID':
      return 'The policy definition is invalid (see the Decision Call for details).';
    case 'DECISION_STATE_TOO_LARGE':
      return "The state is larger than the model's or policy's limit.";
    case 'DECISION_CANDIDATE_INVALID':
      return "The candidates don't match what this question or policy expects.";
    case 'DECISION_LOW_CONFIDENCE':
      return 'The answer came back below the minimum confidence threshold.';
    case 'DECISION_NO_MATCH':
      return 'No candidate matched.';
    case 'DECISION_UNSUPPORTED_MODALITY':
      return "The state includes a modality this backend doesn't accept.";
    case 'DECISION_CANDIDATE_LIMIT_EXCEEDED':
      return 'More candidates were supplied than the policy allows.';
    case 'DECISION_THROUGHPUT_BUDGET_EXHAUSTED':
      return "This deployment's throughput budget is exhausted right now.";
    case 'DECISION_BACKEND_NOT_REGISTERED':
      return "The family's adapter isn't registered on this site.";
    case 'DECISION_FAILED':
      return 'The decision failed for an internal reason that is not shown here to avoid leaking provider details.';
    default:
      return `The decision failed (${code}).`;
  }
}

interface DecisionPlaygroundPanelProps {
  /** Incremented by the Playground header's Run button; each change triggers one run. */
  runRequest: number;
  onRunningChange?: (running: boolean) => void;
}

type PolicyMode = 'published' | 'adhoc';

interface DecisionCandidate {
  id: string;
  description: string;
}

const chevron = <ChevronDown className="h-3.5 w-3.5 text-steel" strokeWidth={1.8} />;

/** Bordered panel with the same eyebrow header as the Prompt / Response panels. */
function Panel({
  title,
  aside,
  className,
  children,
}: {
  title: string;
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn('flex min-h-[260px] min-w-0 flex-col rounded border border-line bg-panel', className)}>
      <div className="flex items-center justify-between gap-3 border-b border-line px-3.5 py-2.5">
        <span className="flex-none font-mono text-eyebrow font-medium uppercase text-steel">{title}</span>
        {aside}
      </div>
      {children}
    </div>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="mb-1 font-mono text-[11px] uppercase text-steel-soft">{children}</div>;
}

function ResultReadout({ running, result }: { running: boolean; result: RunDecisionResult | null }) {
  if (running) {
    return (
      <span className="flex items-center gap-1.5 font-mono text-[11.5px] text-steel">
        <StatusDot variant="run" />
        running
      </span>
    );
  }
  if (!result) return null;
  const ok = result.status === 'success';
  const segments: string[] = [result.status];
  const response = result.response;
  if (response?.latency_ms !== undefined && response?.latency_ms !== null) {
    segments.push(`${response.latency_ms}ms`);
  }
  const tokens = (response?.usage?.input_tokens || 0) + (response?.usage?.output_tokens || 0);
  if (tokens > 0) segments.push(`${tokens} tok`);
  if (response?.usage?.cost) segments.push(`$${response.usage.cost.toFixed(6)}`);
  return (
    <span className="flex min-w-0 items-center gap-1.5 font-mono text-[11.5px]">
      <StatusDot variant={ok ? 'ok' : 'fail'} />
      <span className={cn('truncate', ok ? 'text-steel' : 'text-signal-ink')}>{segments.join(' · ')}</span>
    </span>
  );
}

export function DecisionPlaygroundPanel({ runRequest, onRunningChange }: DecisionPlaygroundPanelProps) {
  const { hasCapability } = usePermissions();
  const isAdmin = hasCapability('decision.admin');
  const canAuthor = hasCapability('decision.author');

  // Models and deployments
  const [models, setModels] = useState<DecisionModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [selectedDeployment, setSelectedDeployment] = useState<string>(AUTO_DEPLOYMENT);

  // Policy vs ad-hoc mode
  const [policyMode, setPolicyMode] = useState<PolicyMode>('published');
  const [selectedPolicy, setSelectedPolicy] = useState<string>('');
  const [adHocDefinition, setAdHocDefinition] = useState<PolicyDefinition | null>(() =>
    newPolicyDefinition('playground_ad_hoc')
  );
  const [policies, setPolicies] = useState<{ name: string; policy_name?: string }[]>([]);
  const [policiesLoading, setPoliciesLoading] = useState(true);

  // State and candidates
  const [state, setState] = useState<string>('');
  const [candidates, setCandidates] = useState<DecisionCandidate[]>([]);
  const [candidateInput, setCandidateInput] = useState<string>('');

  // Result
  const [result, setResult] = useState<RunDecisionResult | null>(null);
  const [resultLoading, setResultLoading] = useState(false);

  const currentModel = models.find((m) => m.name === selectedModel);
  const deployments = currentModel?.deployments ?? [];
  const stateBytes = new TextEncoder().encode(state).length;
  // 0/undefined means the model has no declared limit -- treat it as "not enforced
  // client-side" rather than silently turning it into a false "0 bytes allowed" ceiling
  // that flags every non-empty state as too large.
  const stateLimit = currentModel?.state_limit && currentModel.state_limit > 0
    ? currentModel.state_limit
    : null;
  const stateTooLarge = stateLimit !== null && stateBytes > stateLimit;

  useEffect(() => {
    onRunningChange?.(resultLoading);
  }, [resultLoading, onRunningChange]);

  // Load models on mount
  useEffect(() => {
    (async () => {
      setModelsLoading(true);
      try {
        const loadedModels = await listDecisionModels();
        setModels(loadedModels);
        if (loadedModels.length > 0) {
          setSelectedModel(loadedModels[0].name);
        }
      } catch (error) {
        toast.error(`Failed to load decision models: ${getFrappeErrorMessage(error)}`);
      } finally {
        setModelsLoading(false);
      }
    })();
  }, []);

  // Load published, enabled Decision Policies for the "Policy" mode picker
  useEffect(() => {
    (async () => {
      setPoliciesLoading(true);
      try {
        const rows = await db.getDocList(doctype['Decision Policy'], {
          fields: ['name', 'policy_name'],
          filters: [
            ['enabled', '=', 1],
            ['current_version', '!=', ''],
          ],
          limit: 200,
        });
        setPolicies((rows as { name: string; policy_name?: string }[]) || []);
      } catch (error) {
        toast.error(`Failed to load decision policies: ${getFrappeErrorMessage(error)}`);
      } finally {
        setPoliciesLoading(false);
      }
    })();
  }, []);

  const handleRun = async () => {
    if (resultLoading) return;
    if (!selectedModel) {
      toast.error('Select a model');
      return;
    }

    if (policyMode === 'published' && !selectedPolicy) {
      toast.error('Select a policy');
      return;
    }

    if (policyMode === 'adhoc' && !adHocDefinition) {
      toast.error('Define ad-hoc questions');
      return;
    }

    setResultLoading(true);
    try {
      const runParams: Parameters<typeof runDecision>[0] = {
        decision_model: selectedModel,
        state: state || '{}',
        origin_type: 'Playground',
      };

      if (selectedDeployment !== AUTO_DEPLOYMENT) {
        runParams.pinned_deployment = selectedDeployment;
      }

      if (candidates.length > 0) {
        runParams.candidates = candidates;
      }

      if (policyMode === 'published') {
        runParams.policy = selectedPolicy;
      } else if (policyMode === 'adhoc' && adHocDefinition) {
        runParams.definition = adHocDefinition as unknown as Record<string, unknown>;
      }

      setResult(await runDecision(runParams));
    } catch (error) {
      toast.error(`Failed to run decision: ${getFrappeErrorMessage(error)}`);
    } finally {
      setResultLoading(false);
    }
  };

  // The header Run button lives in PlaygroundShell; it signals here via runRequest.
  const handleRunRef = useRef(handleRun);
  handleRunRef.current = handleRun;
  useEffect(() => {
    if (runRequest > 0) void handleRunRef.current();
  }, [runRequest]);

  const handleAddCandidate = () => {
    if (!candidateInput.trim()) {
      toast.error('Enter a candidate ID');
      return;
    }
    setCandidates([...candidates, { id: candidateInput.trim(), description: '' }]);
    setCandidateInput('');
  };

  const handleRemoveCandidate = (index: number) => {
    setCandidates(candidates.filter((_, i) => i !== index));
  };

  if (modelsLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-paper">
        <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
      </div>
    );
  }

  if (models.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-paper p-6 text-center">
        <AlertCircle className="mb-4 h-8 w-8 text-steel-soft" />
        <p className="mb-2 font-medium text-ink">No decision models available</p>
        <p className="text-sm text-steel-soft">Set up a Decision model in AI providers & models first.</p>
      </div>
    );
  }

  // A provider can host more than one deployment of the same model; only then is the
  // provider model id needed to tell them apart.
  const providerCounts = deployments.reduce<Record<string, number>>((acc, d) => {
    acc[d.provider] = (acc[d.provider] || 0) + 1;
    return acc;
  }, {});

  const isAdHoc = policyMode === 'adhoc';

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      {/* Config strip -- same cell pattern as the Playground tab's ConfigStrip */}
      <div className="px-5 pt-[18px]">
        <div
          className={cn(
            'grid rounded border border-line bg-panel max-lg:grid-cols-2',
            isAdHoc ? 'grid-cols-3' : 'grid-cols-4',
            '[&>div:not(:last-child)]:border-r [&>div]:border-line'
          )}
        >
          <ConfigStripCell label="Model" hint="Canonical decision model for this run">
            <Select
              value={selectedModel}
              onValueChange={(v) => {
                setSelectedModel(v);
                setSelectedDeployment(AUTO_DEPLOYMENT);
              }}
            >
              <SelectTrigger className={flushTriggerClass} icon={chevron}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {models.map((model) => (
                  <SelectItem key={model.name} value={model.name}>
                    {model.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </ConfigStripCell>

          <ConfigStripCell
            label="Provider"
            hint="Which provider serves the model. Auto follows the deployment priority and fails over down the chain; picking one pins the run to it, with no failover."
          >
            <Select
              value={selectedDeployment}
              onValueChange={setSelectedDeployment}
              disabled={deployments.length === 0}
            >
              <SelectTrigger className={flushTriggerClass} icon={chevron}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={AUTO_DEPLOYMENT}>Auto (failover)</SelectItem>
                {deployments.map((dep) => (
                  <SelectItem key={dep.name} value={dep.name}>
                    {dep.provider || dep.deployment_name || dep.name}
                    {providerCounts[dep.provider] > 1 && dep.provider_model_id
                      ? ` · ${dep.provider_model_id}`
                      : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </ConfigStripCell>

          <ConfigStripCell
            label="Mode"
            hint={canAuthor ? 'Run a published policy, or define questions ad hoc' : 'Ad hoc needs decision.author'}
          >
            <Select value={policyMode} onValueChange={(v) => setPolicyMode(v as PolicyMode)}>
              <SelectTrigger className={flushTriggerClass} icon={chevron}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="published">Published policy</SelectItem>
                <SelectItem value="adhoc" disabled={!canAuthor}>
                  Ad hoc
                </SelectItem>
              </SelectContent>
            </Select>
          </ConfigStripCell>

          {!isAdHoc && (
            <ConfigStripCell label="Policy">
              <Select value={selectedPolicy} onValueChange={setSelectedPolicy}>
                <SelectTrigger className={flushTriggerClass} icon={chevron}>
                  <SelectValue placeholder={policiesLoading ? 'Loading…' : 'Select a policy'} />
                </SelectTrigger>
                <SelectContent>
                  {!policiesLoading && policies.length === 0 && (
                    <div className="px-2 py-1.5 text-sm text-muted-foreground">
                      No published policies yet.
                    </div>
                  )}
                  {policies.map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      {p.policy_name || p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </ConfigStripCell>
          )}
        </div>
      </div>

      <div
        className={cn(
          'grid min-h-[340px] flex-1 grid-cols-1 gap-4 p-5',
          isAdHoc ? 'lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_minmax(0,1fr)]' : 'lg:grid-cols-2'
        )}
      >
        {isAdHoc && adHocDefinition && (
          <Panel title="Definition" className="h-full">
            <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
              <QuestionBuilder value={adHocDefinition} onChange={setAdHocDefinition} />
            </div>
          </Panel>
        )}

        {/* Input: state + candidates */}
        <Panel
          title="State"
          className="h-full"
          aside={
            <span
              className={cn('font-mono text-[11.5px]', stateTooLarge ? 'text-status-critical' : 'text-steel-soft')}
              title={stateTooLarge ? `Exceeds the model limit by ${stateBytes - (stateLimit ?? 0)} bytes` : undefined}
            >
              {stateLimit !== null ? `${stateBytes} / ${stateLimit} B` : `${stateBytes} B`}
            </span>
          }
        >
          <Textarea
            value={state}
            onChange={(e) => setState(e.target.value)}
            placeholder={'{"request": "..."}\n\nJSON the state bindings read from.'}
            aria-label="State JSON"
            className="min-h-[180px] flex-1 resize-none rounded-none border-0 px-3.5 py-3 font-mono text-xs leading-relaxed shadow-none placeholder:text-steel focus-visible:ring-0"
          />

          <div className="space-y-2 border-t border-line px-3.5 py-2.5">
            <div
              className="cursor-help font-mono text-[11px] uppercase text-steel-soft underline decoration-dotted decoration-line underline-offset-2"
              title="Runtime options for select questions, sent alongside the state"
            >
              Candidates · {candidates.length}
            </div>
            <div className="flex gap-2">
              <Input
                size="sm"
                value={candidateInput}
                onChange={(e) => setCandidateInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddCandidate();
                  }
                }}
                placeholder="Candidate ID"
                className="font-mono"
              />
              <Button onClick={handleAddCandidate} variant="outline" size="sm" className="gap-1">
                <Plus className="h-3.5 w-3.5" />
                Add
              </Button>
            </div>
            {candidates.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {candidates.map((candidate, index) => (
                  <span
                    key={index}
                    className="inline-flex items-center gap-1 rounded border border-line bg-canvas py-0.5 pl-2 pr-1 font-mono text-xs text-ink"
                  >
                    {candidate.id}
                    <button
                      type="button"
                      onClick={() => handleRemoveCandidate(index)}
                      aria-label={`Remove ${candidate.id}`}
                      className="rounded p-0.5 text-steel hover:text-ink"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </Panel>

        {/* Result */}
        <Panel title="Result" className="h-full" aside={<ResultReadout running={resultLoading} result={result} />}>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {!result ? (
              <p className="px-3.5 py-3 text-[13.5px] text-steel-soft">
                {resultLoading ? 'Running…' : 'Run a decision to see the answers here.'}
              </p>
            ) : (
              <div className="divide-y divide-line">
                {result.status !== 'success' && (
                  <div className="px-3.5 py-3 text-[12.5px] text-signal-ink">
                    <div className="font-medium">
                      {result.response?.error_code
                        ? describeDecisionErrorCode(result.response.error_code)
                        : `The decision did not complete (status: ${result.status}).`}
                    </div>
                    {result.response?.error_code && (
                      <div className="mt-1 font-mono text-xs opacity-80">{result.response.error_code}</div>
                    )}
                    {result.fallback_action && (
                      <div className="mt-1 text-xs">Fallback applied: {result.fallback_action}</div>
                    )}
                  </div>
                )}

                {result.response && (
                  <>
                    {Object.keys(result.response.answers || {}).length > 0 && (
                      <div className="space-y-2 px-3.5 py-3">
                        <Eyebrow>Answers</Eyebrow>
                        {Object.entries(result.response.answers).map(([qid, answer]: [string, DecisionAnswer]) => (
                          <div key={qid} className="rounded bg-canvas px-2.5 py-2">
                            <div className="flex items-baseline justify-between gap-2">
                              <span className="truncate font-mono text-xs text-steel">{qid}</span>
                              {answer.confidence !== null && answer.confidence !== undefined && (
                                <span className="flex-none font-mono text-[11px] text-steel-soft">
                                  conf {(answer.confidence * 100).toFixed(0)}%
                                </span>
                              )}
                            </div>
                            <code className="text-sm text-ink">{String(answer.value)}</code>

                            {answer.probabilities && Object.entries(answer.probabilities).length > 0 && (
                              <div className="mt-1.5 space-y-1">
                                {Object.entries(answer.probabilities).map(([option, prob]) => (
                                  <div key={option} className="flex items-center justify-between gap-2 text-xs">
                                    <span className="truncate text-steel">{option}</span>
                                    <div className="flex flex-none items-center gap-1">
                                      <div className="h-1.5 w-20 overflow-hidden rounded bg-line">
                                        <div
                                          className="h-full bg-accent-default"
                                          style={{ width: `${(prob as number) * 100}%` }}
                                        />
                                      </div>
                                      <span className="w-8 text-right font-mono text-steel-soft">
                                        {((prob as number) * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 px-3.5 py-3 text-xs">
                      {result.response.gate_result && (
                        <>
                          <dt className="text-steel-soft">Gate</dt>
                          <dd className="font-mono text-ink">{result.response.gate_result}</dd>
                        </>
                      )}
                      <dt className="text-steel-soft">Provider</dt>
                      <dd className="truncate font-mono text-ink">{result.response.identity?.provider || '-'}</dd>
                      <dt className="text-steel-soft">Deployment</dt>
                      <dd className="truncate font-mono text-ink">{result.response.identity?.deployment || '-'}</dd>
                      <dt className="text-steel-soft">Provider model</dt>
                      <dd className="truncate font-mono text-ink">
                        {result.response.identity?.provider_model_id || '-'}
                      </dd>
                      {result.response.deployment_fallback_chain?.length > 0 && (
                        <>
                          <dt className="text-steel-soft">Failover</dt>
                          <dd className="font-mono text-steel">
                            {result.response.deployment_fallback_chain.join(' → ')}
                            <span className="text-steel-soft">
                              {' '}({result.response.deployment_fallback_count} fallbacks)
                            </span>
                          </dd>
                        </>
                      )}
                    </dl>
                  </>
                )}

                {(result.decision_call || (isAdmin && result.response)) && (
                  <div className="space-y-2 px-3.5 py-2.5">
                    {result.decision_call && (
                      <a
                        href={`/executions/decisions/${result.decision_call}`}
                        className="inline-flex items-center gap-1 font-mono text-xs text-steel hover:text-ink"
                      >
                        Decision Call {result.decision_call}
                        <ArrowUpRight className="h-3 w-3" />
                      </a>
                    )}
                    {isAdmin && result.response && (
                      <details>
                        <summary className="cursor-pointer font-mono text-[11px] uppercase text-steel-soft hover:text-steel">
                          Raw response
                        </summary>
                        <pre className="mt-2 overflow-x-auto rounded bg-canvas p-2 font-mono text-xs text-steel-soft">
                          {JSON.stringify(result.response, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
