import { useState, useEffect } from 'react';
import { Loader2, AlertCircle, Info } from 'lucide-react';
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
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface DecisionCompareViewProps {
  running: boolean;
}

type CompareMode = 'deployments' | 'models';

interface DecisionCandidate {
  id: string;
  description: string;
}

export function DecisionCompareView({ running }: DecisionCompareViewProps) {
  // Compare mode selection
  const [compareMode, setCompareMode] = useState<CompareMode>('deployments');

  // Models
  const [models, setModels] = useState<DecisionModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);

  // Deployments mode state
  const [selectedModelForDeploy, setSelectedModelForDeploy] = useState<string>('');
  const [selectedDeployment1, setSelectedDeployment1] = useState<string>('');
  const [selectedDeployment2, setSelectedDeployment2] = useState<string>('');

  // Models mode state
  const [selectedModel1, setSelectedModel1] = useState<string>('');
  const [selectedModel2, setSelectedModel2] = useState<string>('');

  // Common state
  const [state, setState] = useState<string>('');
  const [candidates, setCandidates] = useState<DecisionCandidate[]>([]);
  const [candidateInput, setCandidateInput] = useState<string>('');

  // Results
  const [result1, setResult1] = useState<RunDecisionResult | null>(null);
  const [result2, setResult2] = useState<RunDecisionResult | null>(null);
  const [comparing, setComparing] = useState(false);

  const currentModel = models.find((m) => m.name === selectedModelForDeploy);
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
          setSelectedModelForDeploy(loadedModels[0].name);
          setSelectedModel1(loadedModels[0].name);
          if (loadedModels.length > 1) {
            setSelectedModel2(loadedModels[1].name);
          } else {
            setSelectedModel2(loadedModels[0].name);
          }
        }
      } catch (error) {
        toast.error(`Failed to load decision models: ${getFrappeErrorMessage(error)}`);
      } finally {
        setModelsLoading(false);
      }
    })();
  }, []);

  const handleCompare = async () => {
    if (compareMode === 'deployments') {
      if (!selectedModelForDeploy || !selectedDeployment1 || !selectedDeployment2) {
        toast.error('Select a model and two deployments');
        return;
      }
    } else {
      if (!selectedModel1 || !selectedModel2) {
        toast.error('Select two models');
        return;
      }
    }

    setComparing(true);
    try {
      const baseParams = {
        state: state || '{}',
        origin_type: 'Playground' as const,
        candidates: candidates.length > 0 ? candidates : undefined,
      };

      let params1: Parameters<typeof runDecision>[0];
      let params2: Parameters<typeof runDecision>[0];

      if (compareMode === 'deployments') {
        params1 = {
          ...baseParams,
          decision_model: selectedModelForDeploy,
          pinned_deployment: selectedDeployment1,
        };
        params2 = {
          ...baseParams,
          decision_model: selectedModelForDeploy,
          pinned_deployment: selectedDeployment2,
        };
      } else {
        params1 = {
          ...baseParams,
          decision_model: selectedModel1,
        };
        params2 = {
          ...baseParams,
          decision_model: selectedModel2,
        };
      }

      const [res1, res2] = await Promise.all([
        runDecision(params1),
        runDecision(params2),
      ]);

      setResult1(res1);
      setResult2(res2);
    } catch (error) {
      toast.error(`Failed to compare decisions: ${getFrappeErrorMessage(error)}`);
    } finally {
      setComparing(false);
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
      <div className="flex flex-1 flex-col gap-4 p-5">
        {/* Configuration Panel */}
        <div className="rounded border border-line bg-panel p-4">
          <h3 className="mb-4 font-medium text-ink">Comparison</h3>

          {/* Compare mode */}
          <div className="mb-4">
            <label className="mb-2 block text-sm font-medium text-ink">Compare</label>
            <Tabs value={compareMode} onValueChange={(value) => setCompareMode(value as CompareMode)}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="deployments">Deployments</TabsTrigger>
                <TabsTrigger value="models">Models</TabsTrigger>
              </TabsList>
            </Tabs>
            <FormDescription>
              {compareMode === 'deployments'
                ? 'Run the same model on two different deployments'
                : 'Run two different models on the same state'}
            </FormDescription>
          </div>

          {compareMode === 'deployments' ? (
            <>
              {/* Model picker for deployment mode */}
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-ink">Model</label>
                <Select value={selectedModelForDeploy} onValueChange={setSelectedModelForDeploy}>
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
                <FormDescription>Decision model to test</FormDescription>
              </div>

              {/* Deployment 1 */}
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-ink">Deployment 1</label>
                <Select value={selectedDeployment1} onValueChange={setSelectedDeployment1}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select first deployment…" />
                  </SelectTrigger>
                  <SelectContent>
                    {currentModel?.deployments?.map((dep) => (
                      <SelectItem key={dep.name} value={dep.name}>
                        {dep.deployment_name || dep.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>First deployment for comparison</FormDescription>
              </div>

              {/* Deployment 2 */}
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-ink">Deployment 2</label>
                <Select value={selectedDeployment2} onValueChange={setSelectedDeployment2}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select second deployment…" />
                  </SelectTrigger>
                  <SelectContent>
                    {currentModel?.deployments?.map((dep) => (
                      <SelectItem key={dep.name} value={dep.name}>
                        {dep.deployment_name || dep.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>Second deployment for comparison</FormDescription>
              </div>
            </>
          ) : (
            <>
              {/* Model 1 for models mode */}
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-ink">Model 1</label>
                <Select value={selectedModel1} onValueChange={setSelectedModel1}>
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
                <FormDescription>First model for comparison</FormDescription>
              </div>

              {/* Model 2 for models mode */}
              <div className="mb-4">
                <label className="mb-2 block text-sm font-medium text-ink">Model 2</label>
                <Select value={selectedModel2} onValueChange={setSelectedModel2}>
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
                <FormDescription>Second model for comparison</FormDescription>
              </div>
            </>
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

        {/* Compare button */}
        <Button onClick={handleCompare} disabled={running || comparing} className="w-full">
          {running || comparing ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Comparing
            </>
          ) : (
            'Compare'
          )}
        </Button>

        {/* Results */}
        {(result1 || result2) && (
          <div className="rounded border border-line bg-panel p-4">
            <h3 className="mb-4 font-medium text-ink">Results</h3>

            <div className="grid grid-cols-2 gap-4">
              {/* Left side result */}
              <div className="rounded bg-canvas p-3">
                <h4 className="mb-3 text-sm font-medium text-ink">
                  {compareMode === 'deployments' ? 'Deployment 1' : 'Model 1'}
                </h4>
                {result1 ? (
                  <ResultColumn result={result1} />
                ) : (
                  <div className="text-xs text-steel-soft">Waiting for comparison</div>
                )}
              </div>

              {/* Right side result */}
              <div className="rounded bg-canvas p-3">
                <h4 className="mb-3 text-sm font-medium text-ink">
                  {compareMode === 'deployments' ? 'Deployment 2' : 'Model 2'}
                </h4>
                {result2 ? (
                  <ResultColumn result={result2} />
                ) : (
                  <div className="text-xs text-steel-soft">Waiting for comparison</div>
                )}
              </div>
            </div>

            {/* Comparison metrics */}
            {result1?.response && result2?.response && (
              <div className="mt-4 border-t border-line pt-4">
                <h4 className="mb-3 text-sm font-medium text-ink">Metrics Comparison</h4>
                <MetricsComparison result1={result1} result2={result2} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

interface ResultColumnProps {
  result: RunDecisionResult;
}

function ResultColumn({ result }: ResultColumnProps) {
  return (
    <div className="space-y-3">
      <div>
        <div className="text-xs font-medium uppercase text-steel-soft">Status</div>
        <Badge variant={result.status === 'success' ? 'default' : 'destructive'} className="text-xs">
          {result.status}
        </Badge>
      </div>

      {result.response && (
        <>
          {/* Answers summary */}
          <div>
            <div className="mb-1 text-xs font-medium uppercase text-steel-soft">Answers</div>
            <div className="space-y-1">
              {Object.entries(result.response.answers).map(([qid, answer]: [string, DecisionAnswer]) => (
                <div key={qid} className="text-xs">
                  <div className="font-mono text-ink">{qid}</div>
                  <div className="flex items-center gap-1">
                    <code className="text-xs text-steel">{String(answer.value)}</code>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="h-3 w-3 text-steel-soft" />
                      </TooltipTrigger>
                      <TooltipContent>{(answer.confidence * 100).toFixed(0)}% confident</TooltipContent>
                    </Tooltip>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Deployment info */}
          {result.response.identity && (
            <div>
              <div className="mb-1 text-xs font-medium uppercase text-steel-soft">Deployment</div>
              <div className="font-mono text-xs text-steel">{result.response.identity.deployment}</div>
            </div>
          )}

          {/* Metrics */}
          <div>
            <div className="mb-1 text-xs font-medium uppercase text-steel-soft">Metrics</div>
            <div className="space-y-1 font-mono text-xs">
              <div className="flex justify-between">
                <span className="text-steel-soft">Latency:</span>
                <span className="text-ink">{result.response.latency_ms}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-steel-soft">Tokens:</span>
                <span className="text-ink">
                  {(result.response.usage?.input_tokens || 0) + (result.response.usage?.output_tokens || 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-steel-soft">Cost:</span>
                <span className="text-ink">${(result.response.usage?.cost || 0).toFixed(6)}</span>
              </div>
            </div>
          </div>
        </>
      )}

      {result.status !== 'success' && (
        <Alert variant="destructive" className="mt-2">
          <AlertCircle className="h-3 w-3" />
          <AlertDescription className="text-xs">{result.status}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}

interface MetricsComparisonProps {
  result1: RunDecisionResult;
  result2: RunDecisionResult;
}

function MetricsComparison({ result1, result2 }: MetricsComparisonProps) {
  const latency1 = result1.response?.latency_ms || 0;
  const latency2 = result2.response?.latency_ms || 0;
  const tokens1 = (result1.response?.usage?.input_tokens || 0) + (result1.response?.usage?.output_tokens || 0);
  const tokens2 = (result2.response?.usage?.input_tokens || 0) + (result2.response?.usage?.output_tokens || 0);
  const cost1 = result1.response?.usage?.cost || 0;
  const cost2 = result2.response?.usage?.cost || 0;

  const getDelta = (val1: number, val2: number, isLower: boolean = true): string => {
    if (val1 === val2) return '—';
    const delta = ((val2 - val1) / val1 * 100).toFixed(0);
    const sign = val2 > val1 ? '+' : '';
    const isWorse = isLower ? val2 > val1 : val2 < val1;
    return `${sign}${delta}% ${isWorse ? '⬆' : '⬇'}`;
  };

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="grid grid-cols-3 gap-2 rounded bg-canvas p-2">
        <div className="text-steel-soft">Metric</div>
        <div className="text-steel-soft">Left</div>
        <div className="text-steel-soft">Right</div>
      </div>

      <div className="grid grid-cols-3 gap-2 border-t border-line pt-2">
        <div className="text-steel-soft">Latency (ms)</div>
        <div className="text-ink">{latency1}</div>
        <div className="text-ink">
          {latency2}
          <div className="text-xs text-steel-soft">{getDelta(latency1, latency2, true)}</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="text-steel-soft">Tokens</div>
        <div className="text-ink">{tokens1}</div>
        <div className="text-ink">
          {tokens2}
          <div className="text-xs text-steel-soft">{getDelta(tokens1, tokens2, true)}</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="text-steel-soft">Cost</div>
        <div className="text-ink">${cost1.toFixed(6)}</div>
        <div className="text-ink">
          ${cost2.toFixed(6)}
          <div className="text-xs text-steel-soft">{getDelta(cost1, cost2, true)}</div>
        </div>
      </div>
    </div>
  );
}
