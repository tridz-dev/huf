import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Loader2, Play } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getAgents } from '@/services/agentApi';
import { getProviders, getModels } from '@/services/providerApi';
import { runAgentSync } from '@/services/consoleApi';
import type { AgentDoc, AIProvider, AIModel } from '@/types/agent.types';
import { settleAll } from '@/lib/settleAll';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

export { ConsolePage };
export default ConsolePage;

function ConsolePage() {
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [agents, setAgents] = useState<AgentDoc[]>([]);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);

  const [agentName, setAgentName] = useState<string>('');
  const [provider, setProvider] = useState<string>('');
  const [model, setModel] = useState<string>('');
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState<string | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      const errorLabels = ['agents', 'providers'];
      const [agentsRes, providersRes] = await settleAll(
        [getAgents(), getProviders()],
        (index, error) => {
          toast.error(`Failed to load ${errorLabels[index]}: ${getFrappeErrorMessage(error)}`);
        },
      );
      if (agentsRes) setAgents(Array.isArray(agentsRes) ? agentsRes : agentsRes.items);
      if (providersRes) setProviders(Array.isArray(providersRes) ? providersRes : providersRes.items);
      setLoading(false);
    })();
  }, []);

  useEffect(() => {
    if (!provider) {
      setModels([]);
      return;
    }
    getModels(provider).then(setModels);
  }, [provider]);

  const handleAgentChange = (value: string) => {
    setAgentName(value);
    const agent = agents.find((a) => a.name === value);
    setProvider(agent?.provider || '');
    setModel(agent?.model || '');
  };

  const handleRun = async () => {
    if (!agentName || !prompt.trim()) {
      toast.error('Agent and prompt are required');
      return;
    }
    setRunning(true);
    setResponse(null);
    setLastRunId(null);
    const result = await runAgentSync({
      agent_name: agentName,
      prompt: prompt.trim(),
      provider: provider || undefined,
      model: model || undefined,
      // The Console is an explicit direct-execution surface: it exists to run
      // an agent synchronously and show the final response in the same
      // request, so it always opts out of the queue-first default.
      now: true,
    });
    setRunning(false);
    if (!result.success) {
      toast.error(result.error || 'Agent run failed');
      return;
    }
    setResponse(result.response ?? '');
    setLastRunId(result.agent_run_id ?? null);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Console</h1>
          <p className="text-sm text-steel">
            Run any agent synchronously with a one-off prompt, outside of chat.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Run Agent</CardTitle>
            <CardDescription>Provider/model default from the agent but can be overridden.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label>Agent</Label>
                <Select value={agentName} onValueChange={handleAgentChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select agent" />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((a) => (
                      <SelectItem key={a.name} value={a.name}>
                        {a.agent_name || a.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Provider</Label>
                <Select
                  value={provider}
                  onValueChange={(v) => {
                    setProvider(v);
                    setModel('');
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Default" />
                  </SelectTrigger>
                  <SelectContent>
                    {providers.map((p) => (
                      <SelectItem key={p.name} value={p.name}>
                        {p.provider_name || p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Model</Label>
                <Select value={model} onValueChange={setModel} disabled={!provider}>
                  <SelectTrigger>
                    <SelectValue placeholder="Default" />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m.name} value={m.name}>
                        {m.model_name || m.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Prompt</Label>
              <Textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Type a prompt to send to this agent..."
                className="min-h-[120px]"
              />
            </div>

            <Button onClick={handleRun} disabled={running || !agentName || !prompt.trim()} className="gap-2">
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Run
            </Button>
          </CardContent>
        </Card>

        {(response !== null || running) && (
          <Card>
            <CardHeader>
              <CardTitle>Response</CardTitle>
              {lastRunId && (
                <CardDescription>
                  <Link to={`/executions/${lastRunId}`} className="text-primary hover:underline">
                    View run {lastRunId}
                  </Link>
                </CardDescription>
              )}
            </CardHeader>
            <CardContent>
              {running ? (
                <div className="flex items-center gap-2 text-steel text-sm py-4">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Running...
                </div>
              ) : (
                <div className="rounded-none bg-paper-deep p-3 text-sm whitespace-pre-wrap break-words max-h-[400px] overflow-auto">
                  {response || 'No response returned.'}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
