import { useState, useEffect } from 'react';
import { Loader2, AlertCircle, ExternalLink, Info } from 'lucide-react';
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
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FormDescription } from '@/components/ui/form';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  listDecisionModels,
  runDecision,
  type DecisionModel,
  type RunDecisionResult,
  type DecisionAnswer,
} from '@/services/decisionApi';
import { QuestionBuilder, type PolicyDefinition } from '@/components/decision/QuestionBuilder';
import { usePermissions } from '@/contexts/PermissionsContext';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface DecisionPlaygroundPanelProps {
  running: boolean;
  onRun: (result: RunDecisionResult) => void;
}

type PolicyMode = 'published' | 'adhoc';

interface DecisionCandidate {
  id: string;
  description: string;
}

export function DecisionPlaygroundPanel({ running, onRun }: DecisionPlaygroundPanelProps) {
  const { hasCapability } = usePermissions();
  const isAdmin = hasCapability('decision.admin');

  // Models and deployments
  const [models, setModels] = useState<DecisionModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [selectedDeployment, setSelectedDeployment] = useState<string>('auto');

  // Policy vs ad-hoc mode
  const [policyMode, setPolicyMode] = useState<PolicyMode>('published');
  const [selectedPolicy, setSelectedPolicy] = useState<string>('');
  const [adHocDefinition, setAdHocDefinition] = useState<PolicyDefinition | null>(null);

  // State and candidates
  const [state, setState] = useState<string>('');
  const [candidates, setCandidates] = useState<DecisionCandidate[]>([]);
  const [candidateInput, setCandidateInput] = useState<string>('');

  // Result
  const [result, setResult] = useState<RunDecisionResult | null>(null);
  const [resultLoading, setResultLoading] = useState(false);

  const currentModel = models.find((m) => m.name === selectedModel);
  const stateBytes = new TextEncoder().encode(state).length;
  const stateLimit = currentModel?.state_limit ?? 8000;

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

  const handleRun = async () => {
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

      if (selectedDeployment !== 'auto') {
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

      const runResult = await runDecision(runParams);
      setResult(runResult);
      onRun(runResult);
    } catch (error) {
      toast.error(`Failed to run decision: ${getFrappeErrorMessage(error)}`);
    } finally {
      setResultLoading(false);
    }
  };

  const handleAddCandidate = () => {
    if (!candidateInput.trim()) {
      toast.error('Enter a candidate ID');
      return;
    }
    setCandidates([...candidates, { id: candidateInput, description: '' }]);
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

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto bg-paper">
      <div className="grid flex-1 grid-cols-1 gap-4 p-5 lg:grid-cols-[1fr_1fr]">
        {/* Input Panel */}
        <div className="flex flex-col gap-4 overflow-y-auto">
          <div className="rounded border border-line bg-panel p-4">
            <h3 className="mb-4 font-medium text-ink">Configuration</h3>

            {/* Model picker */}
            <div className="mb-4">
              <label className="mb-2 block text-sm font-medium text-ink">Model</label>
              <Select value={selectedModel} onValueChange={setSelectedModel}>
                <SelectTrigger>
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
              <FormDescription>Decision model for this run</FormDescription>
            </div>

            {/* Deployment selector */}
            <div className="mb-4">
              <label className="mb-2 block text-sm font-medium text-ink">Deployment</label>
              <Select value={selectedDeployment} onValueChange={setSelectedDeployment}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto (default)</SelectItem>
                  {currentModel?.deployments?.map((dep) => (
                    <SelectItem key={dep.name} value={dep.name}>
                      {dep.deployment_name || dep.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>Auto uses the default deployment and failover chain</FormDescription>
            </div>

            {/* Policy mode toggle */}
            <div className="mb-4">
              <label className="mb-2 block text-sm font-medium text-ink">Mode</label>
              <Tabs value={policyMode} onValueChange={(value) => setPolicyMode(value as PolicyMode)}>
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="published">Policy</TabsTrigger>
                  <TabsTrigger value="adhoc" disabled={!hasCapability('decision.author')}>
                    Ad hoc
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <FormDescription>
                {policyMode === 'published'
                  ? 'Run a published policy'
                  : 'Define questions on the fly (requires decision.author)'}
              </FormDescription>
            </div>

            {policyMode === 'published' && (
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-ink">Policy</label>
                <Select value={selectedPolicy} onValueChange={setSelectedPolicy}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a policy…" />
                  </SelectTrigger>
                  <SelectContent>
                    {/* TODO: fetch policies from API */}
                  </SelectContent>
                </Select>
                <FormDescription>Published Decision Policies</FormDescription>
              </div>
            )}

            {policyMode === 'adhoc' && (
              <div className="mb-4 border-t border-line pt-4">
                {adHocDefinition && (
                  <QuestionBuilder
                    value={adHocDefinition}
                    onChange={setAdHocDefinition}
                  />
                )}
              </div>
            )}
          </div>

          {/* State editor */}
          <div className="rounded border border-line bg-panel p-4">
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-ink">State</label>
              <div
                className={`font-mono text-xs ${
                  stateBytes > stateLimit ? 'text-status-critical' : 'text-steel-soft'
                }`}
              >
                {stateBytes} / {stateLimit} bytes
              </div>
            </div>
            <Textarea
              value={state}
              onChange={(e) => setState(e.target.value)}
              placeholder='{"request": "..."}'
              className="mb-2 font-mono text-xs"
              rows={6}
            />
            <FormDescription>Context as JSON</FormDescription>
            {stateBytes > stateLimit && (
              <Alert variant="destructive" className="mt-2">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>State exceeds model limit by {stateBytes - stateLimit} bytes</AlertDescription>
              </Alert>
            )}
          </div>

          {/* Candidates */}
          <div className="rounded border border-line bg-panel p-4">
            <label className="mb-2 block text-sm font-medium text-ink">Candidates</label>
            <div className="mb-2 flex gap-2">
              <Input
                value={candidateInput}
                onChange={(e) => setCandidateInput(e.target.value)}
                placeholder="Candidate ID"
              />
              <Button onClick={handleAddCandidate} variant="outline" size="sm">
                Add
              </Button>
            </div>
            {candidates.length > 0 && (
              <div className="space-y-2">
                {candidates.map((candidate, index) => (
                  <div key={index} className="flex items-center justify-between rounded bg-canvas p-2">
                    <code className="text-xs text-ink">{candidate.id}</code>
                    <Button
                      onClick={() => handleRemoveCandidate(index)}
                      variant="ghost"
                      size="sm"
                      className="h-auto px-2 py-1"
                    >
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
            )}
            <FormDescription>Options for select/score questions</FormDescription>
          </div>

          {/* Run button */}
          <Button onClick={handleRun} disabled={running || resultLoading || !selectedModel} className="w-full">
            {running || resultLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Running
              </>
            ) : (
              'Run'
            )}
          </Button>
        </div>

        {/* Result Panel */}
        <div className="flex flex-col gap-4 overflow-y-auto">
          {result ? (
            <div className="rounded border border-line bg-panel p-4">
              <h3 className="mb-4 font-medium text-ink">Result</h3>

              {/* Status */}
              <div className="mb-4">
                <label className="mb-1 block text-xs font-medium uppercase text-steel-soft">Status</label>
                <Badge variant={result.status === 'success' ? 'default' : 'destructive'}>
                  {result.status}
                </Badge>
              </div>

              {result.response && (
                <>
                  {/* Answers */}
                  <div className="mb-4">
                    <label className="mb-2 block text-xs font-medium uppercase text-steel-soft">Answers</label>
                    {Object.entries(result.response.answers).map(([qid, answer]: [string, DecisionAnswer]) => (
                      <div key={qid} className="mb-3 rounded bg-canvas p-3">
                        <div className="mb-1 font-mono text-xs font-medium text-ink">{qid}</div>
                        <div className="mb-2 flex items-center gap-2">
                          <code className="text-sm text-ink">{String(answer.value)}</code>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="h-3.5 w-3.5 text-steel-soft" />
                            </TooltipTrigger>
                            <TooltipContent>Confidence: {(answer.confidence * 100).toFixed(0)}%</TooltipContent>
                          </Tooltip>
                        </div>

                        {/* Probabilities */}
                        {answer.probabilities && Object.entries(answer.probabilities).length > 0 && (
                          <div className="mb-2">
                            <div className="mb-1 text-xs text-steel-soft">Probabilities</div>
                            <div className="space-y-1">
                              {Object.entries(answer.probabilities).map(([option, prob]) => (
                                <div key={option} className="flex items-center justify-between text-xs">
                                  <span className="text-steel">{option}</span>
                                  <div className="flex items-center gap-1">
                                    <div className="h-2 w-20 overflow-hidden rounded bg-line">
                                      <div
                                        className="h-full bg-accent-default"
                                        style={{ width: `${(prob as number) * 100}%` }}
                                      />
                                    </div>
                                    <span className="font-mono text-steel-soft">{((prob as number) * 100).toFixed(0)}%</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Identity and resolution */}
                  <div className="mb-4 space-y-2 border-t border-line pt-4">
                    <div>
                      <label className="block text-xs font-medium uppercase text-steel-soft">Provider</label>
                      <div className="font-mono text-sm text-ink">{result.response.identity?.provider}</div>
                    </div>
                    <div>
                      <label className="block text-xs font-medium uppercase text-steel-soft">Deployment</label>
                      <div className="font-mono text-sm text-ink">{result.response.identity?.deployment}</div>
                    </div>
                    <div>
                      <label className="block text-xs font-medium uppercase text-steel-soft">Provider Model ID</label>
                      <Badge variant="secondary" className="font-mono text-xs">
                        {result.response.identity?.provider_model_id}
                      </Badge>
                    </div>
                  </div>

                  {/* Failover chain */}
                  {result.response.deployment_fallback_chain?.length > 0 && (
                    <div className="mb-4">
                      <label className="mb-1 block text-xs font-medium uppercase text-steel-soft">
                        Failover chain ({result.response.deployment_fallback_count} fallbacks)
                      </label>
                      <div className="space-y-1">
                        {result.response.deployment_fallback_chain.map((dep, idx) => (
                          <div key={idx} className="font-mono text-xs text-steel-soft">
                            {idx + 1}. {dep}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Metrics */}
                  <div className="mb-4 grid grid-cols-3 gap-2 border-t border-line pt-4">
                    <div>
                      <div className="text-xs font-medium uppercase text-steel-soft">Latency</div>
                      <div className="font-mono text-sm text-ink">
                        {result.response.latency_ms}
                        <span className="text-xs text-steel-soft"> ms</span>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-medium uppercase text-steel-soft">Tokens</div>
                      <div className="font-mono text-sm text-ink">
                        {(result.response.usage?.input_tokens || 0) + (result.response.usage?.output_tokens || 0)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-medium uppercase text-steel-soft">Cost</div>
                      <div className="font-mono text-sm text-ink">
                        ${(result.response.usage?.cost || 0).toFixed(6)}
                      </div>
                    </div>
                  </div>

                  {/* Call link */}
                  {result.decision_call && (
                    <div className="mb-4">
                      <Button
                        asChild
                        variant="outline"
                        size="sm"
                        className="w-full justify-between"
                      >
                        <a href={`/executions/decisions/${result.decision_call}`}>
                          Decision Call {result.decision_call}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </Button>
                    </div>
                  )}

                  {/* Gate result */}
                  {result.response.gate_result && (
                    <div className="mb-4">
                      <label className="mb-1 block text-xs font-medium uppercase text-steel-soft">Gate Result</label>
                      <Badge>{result.response.gate_result}</Badge>
                    </div>
                  )}

                  {/* Raw response (admin only) */}
                  {isAdmin && (
                    <details className="border-t border-line pt-4">
                      <summary className="cursor-pointer text-xs font-medium uppercase text-steel-soft hover:text-steel">
                        Raw response (admin)
                      </summary>
                      <pre className="mt-2 overflow-x-auto rounded bg-canvas p-2 font-mono text-xs text-steel-soft">
                        {JSON.stringify(result.response, null, 2)}
                      </pre>
                    </details>
                  )}
                </>
              )}

              {result.status !== 'success' && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{result.status}</AlertDescription>
                </Alert>
              )}
            </div>
          ) : (
            <div className="flex h-full items-center justify-center rounded border border-line border-dashed bg-canvas">
              <div className="text-center">
                <p className="text-sm text-steel-soft">Run a decision to see results here</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
