import { useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Loader2, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ConsoleConfigForm, type ConsoleConfig } from './ConsoleConfigForm';
import { runAgentSync } from '@/services/consoleApi';
import type { AgentDoc, AIProvider } from '@/types/agent.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface ConsoleCompareProps {
  agents: AgentDoc[];
  providers: AIProvider[];
  configA: ConsoleConfig;
  configB: ConsoleConfig;
  onConfigAChange: (config: ConsoleConfig) => void;
  onConfigBChange: (config: ConsoleConfig) => void;
}

interface CompareResult {
  id: string;
  success?: boolean;
  response?: string;
  agentRunId?: string;
  error?: string;
}

export function ConsoleCompare({
  agents,
  providers,
  configA,
  configB,
  onConfigAChange,
  onConfigBChange,
}: ConsoleCompareProps) {
  const [runningA, setRunningA] = useState(false);
  const [runningB, setRunningB] = useState(false);
  const [resultA, setResultA] = useState<CompareResult | null>(null);
  const [resultB, setResultB] = useState<CompareResult | null>(null);

  const runSide = async (
    config: ConsoleConfig,
    setRunning: (v: boolean) => void,
    setResult: (r: CompareResult | null) => void,
    label: string,
  ) => {
    if (!config.agentName || !config.prompt.trim()) {
      toast.error(`${label}: Agent and prompt are required`);
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
      setResult({
        id: `${label}-${Date.now()}`,
        success: runResult.success,
        response: runResult.response,
        agentRunId: runResult.agent_run_id,
        error: runResult.error,
      });
    } catch (error) {
      toast.error(`${label} run failed: ${getFrappeErrorMessage(error)}`);
    } finally {
      setRunning(false);
    }
  };

  const handleRunBoth = async () => {
    await Promise.all([
      runSide(configA, setRunningA, setResultA, 'A'),
      runSide(configB, setRunningB, setResultB, 'B'),
    ]);
  };

  const renderOutput = (result: CompareResult | null, running: boolean, label: string) => {
    if (running) {
      return (
        <div className="flex h-full items-center justify-center gap-2 text-sm text-steel">
          <Loader2 className="h-4 w-4 animate-spin" />
          Running {label}...
        </div>
      );
    }
    if (result?.success === false) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-destructive">
          <XCircle className="h-6 w-6" />
          <p>{result.error || 'Run failed'}</p>
        </div>
      );
    }
    if (result?.response != null) {
      return (
        <div className="space-y-3 p-4">
          {result.agentRunId && (
            <Link
              to={`/executions/${result.agentRunId}`}
              className="text-xs text-primary hover:underline"
            >
              View run {result.agentRunId}
            </Link>
          )}
          <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
            {result.response}
          </div>
        </div>
      );
    }
    return (
      <div className="flex h-full flex-col items-center justify-center text-sm text-steel">
        <p>Run comparison to see {label}&apos;s response.</p>
      </div>
    );
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-full min-h-0 flex-col lg:flex-row">
        {/* Side A */}
        <div className="flex h-full min-h-0 w-full flex-col border-r border-line bg-panel lg:w-1/2">
          <div className="flex h-9 items-center border-b border-line px-4 text-xs font-medium text-steel">
            A
          </div>
          <div className="flex-1 overflow-hidden">
            <ConsoleConfigForm
              agents={agents}
              providers={providers}
              config={configA}
              onChange={onConfigAChange}
              onRun={() => runSide(configA, setRunningA, setResultA, 'A')}
              running={runningA}
              showEvaluate={false}
              compact
            />
          </div>
        </div>

        {/* Side B */}
        <div className="flex h-full min-h-0 w-full flex-col border-r border-line bg-panel lg:w-1/2">
          <div className="flex h-9 items-center border-b border-line px-4 text-xs font-medium text-steel">
            B
          </div>
          <div className="flex-1 overflow-hidden">
            <ConsoleConfigForm
              agents={agents}
              providers={providers}
              config={configB}
              onChange={onConfigBChange}
              onRun={() => runSide(configB, setRunningB, setResultB, 'B')}
              running={runningB}
              showEvaluate={false}
              compact
            />
          </div>
        </div>
      </div>

      {/* Outputs */}
      <div className="flex min-h-0 flex-1 flex-col border-t border-line bg-background lg:flex-row">
        <div className="flex min-h-0 flex-1 flex-col p-3">
          <Card className="flex h-full flex-col overflow-hidden">
            <CardHeader className="shrink-0 border-b border-line py-2">
              <CardTitle className="text-sm">Output A</CardTitle>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-auto p-0">
              {renderOutput(resultA, runningA, 'A')}
            </CardContent>
          </Card>
        </div>
        <div className="flex min-h-0 flex-1 flex-col p-3">
          <Card className="flex h-full flex-col overflow-hidden">
            <CardHeader className="shrink-0 border-b border-line py-2">
              <CardTitle className="text-sm">Output B</CardTitle>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-auto p-0">
              {renderOutput(resultB, runningB, 'B')}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Floating run-both bar */}
      <div className="flex shrink-0 items-center justify-center border-t border-line bg-panel p-3">
        <Button
          onClick={handleRunBoth}
          disabled={runningA || runningB}
          className="gap-2"
        >
          {runningA || runningB ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : null}
          Run both
        </Button>
      </div>
    </div>
  );
}
