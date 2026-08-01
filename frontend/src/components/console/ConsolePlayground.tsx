import { useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ConsoleConfigForm, type ConsoleConfig } from './ConsoleConfigForm';
import {
  runAgentSync,
  generatePrompt,
  evaluateRun,
  type RunAgentSyncResult,
  type EvaluateRunResult,
} from '@/services/consoleApi';
import type { AgentDoc, AIProvider } from '@/types/agent.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface ConsolePlaygroundProps {
  agents: AgentDoc[];
  providers: AIProvider[];
  config: ConsoleConfig;
  onConfigChange: (config: ConsoleConfig) => void;
}

interface PlaygroundResult extends RunAgentSyncResult {
  evaluation?: EvaluateRunResult;
  agentRunId?: string;
}

export function ConsolePlayground({
  agents,
  providers,
  config,
  onConfigChange,
}: ConsolePlaygroundProps) {
  const [running, setRunning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [result, setResult] = useState<PlaygroundResult | null>(null);

  const handleRun = async () => {
    if (!config.agentName || !config.prompt.trim()) {
      toast.error('Agent and prompt are required');
      return;
    }
    setRunning(true);
    setResult(null);
    try {
      const runResult = await runAgentSync({
        agent_name: config.agentName,
        prompt: config.prompt.trim(),
        provider: config.provider || undefined,
        model: config.model || undefined,
        now: true,
      });
      setResult(runResult);
    } catch (error) {
      toast.error(`Run failed: ${getFrappeErrorMessage(error)}`);
    } finally {
      setRunning(false);
    }
  };

  const handleGenerate = async () => {
    if (!config.prompt.trim()) {
      toast.error('Enter a description to generate a prompt');
      return;
    }
    setGenerating(true);
    try {
      const generated = await generatePrompt({ description: config.prompt.trim() });
      onConfigChange({ ...config, prompt: generated.prompt });
      toast.success('Prompt generated');
    } catch (error) {
      // error already handled by service
    } finally {
      setGenerating(false);
    }
  };

  const handleEvaluate = async () => {
    if (!result?.response || !config.evaluationCriteria.trim()) {
      toast.error('Run the prompt and enter criteria first');
      return;
    }
    setEvaluating(true);
    try {
      const evaluation = await evaluateRun({
        response: result.response,
        criteria: config.evaluationCriteria.trim(),
        provider: config.provider || undefined,
        model: config.model || undefined,
      });
      setResult({ ...result, evaluation });
      toast.success(evaluation.passed ? 'Evaluation passed' : 'Evaluation failed');
    } catch (error) {
      // error already handled by service
    } finally {
      setEvaluating(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <div className="flex h-full min-h-0 w-full flex-col border-r border-line bg-panel lg:w-[420px] xl:w-[480px]">
        <ConsoleConfigForm
          agents={agents}
          providers={providers}
          config={config}
          onChange={onConfigChange}
          onRun={handleRun}
          onGenerate={handleGenerate}
          onEvaluate={handleEvaluate}
          running={running}
          generating={generating}
          evaluating={evaluating}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background p-4">
        <Card className="flex h-full flex-col overflow-hidden">
          <CardHeader className="shrink-0 border-b border-line pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Response</CardTitle>
              {result?.agentRunId && (
                <Link
                  to={`/executions/${result.agentRunId}`}
                  className="text-xs text-primary hover:underline"
                >
                  View run {result.agentRunId}
                </Link>
              )}
            </div>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-auto p-0">
            {running ? (
              <div className="flex h-full items-center justify-center gap-2 text-sm text-steel">
                <Loader2 className="h-4 w-4 animate-spin" />
                Running...
              </div>
            ) : result?.success === false ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-destructive">
                <XCircle className="h-6 w-6" />
                <p>{result.error || 'Run failed'}</p>
              </div>
            ) : result?.response != null ? (
              <div className="space-y-4 p-4">
                {result.evaluation && (
                  <div className="flex items-start gap-3 rounded-md border border-line bg-panel p-3">
                    {result.evaluation.passed ? (
                      <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-600" />
                    ) : (
                      <XCircle className="mt-0.5 h-5 w-5 text-destructive" />
                    )}
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge variant={result.evaluation.passed ? 'default' : 'destructive'}>
                          {result.evaluation.passed ? 'Passed' : 'Failed'}
                        </Badge>
                        <span className="text-xs text-steel">Score: {result.evaluation.score}/100</span>
                      </div>
                      <p className="text-sm text-steel">{result.evaluation.reasoning}</p>
                    </div>
                  </div>
                )}
                <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                  {result.response}
                </div>
              </div>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-steel">
                <p>Run a prompt to see the response here.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
