import { useEffect, useState } from 'react';
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
import { Loader2, Sparkles, Play, ShieldCheck } from 'lucide-react';
import type { PaginatedModelsResponse } from '@/services/providerApi';
import type { AgentDoc, AIProvider, AIModel } from '@/types/agent.types';
import { InstructionsTextarea } from '@/components/agent/InstructionsTextarea';
import { getModels } from '@/services/providerApi';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

export interface ConsoleConfig {
  agentName: string;
  provider: string;
  model: string;
  prompt: string;
  evaluationCriteria: string;
}

interface ConsoleConfigFormProps {
  agents: AgentDoc[];
  providers: AIProvider[];
  config: ConsoleConfig;
  onChange: (config: ConsoleConfig) => void;
  onRun: () => void;
  onGenerate?: () => void;
  onEvaluate?: () => void;
  running?: boolean;
  generating?: boolean;
  evaluating?: boolean;
  showEvaluate?: boolean;
  compact?: boolean;
}

export function ConsoleConfigForm({
  agents,
  providers,
  config,
  onChange,
  onRun,
  onGenerate,
  onEvaluate,
  running,
  generating,
  evaluating,
  showEvaluate = true,
  compact = false,
}: ConsoleConfigFormProps) {
  const [models, setModels] = useState<AIModel[]>([]);

  useEffect(() => {
    if (!config.provider) {
      setModels([]);
      return;
    }
    let cancelled = false;
    getModels(config.provider)
      .then((fetched) => {
        if (!cancelled) {
          setModels(Array.isArray(fetched) ? fetched : (fetched as PaginatedModelsResponse).items);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          toast.error(`Failed to load models: ${getFrappeErrorMessage(error)}`);
          setModels([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [config.provider]);

  const update = (patch: Partial<ConsoleConfig>) => {
    onChange({ ...config, ...patch });
  };

  const DIRECT_AGENT_VALUE = '__direct__';

  const handleAgentChange = (value: string) => {
    if (value === DIRECT_AGENT_VALUE) {
      update({ agentName: '' });
      return;
    }
    const agent = agents.find((a) => a.name === value);
    update({
      agentName: value,
      provider: agent?.provider || '',
      model: agent?.model || '',
    });
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <div className={compact ? 'grid gap-3' : 'grid gap-4 sm:grid-cols-3'}>
        <div className="space-y-2">
          <Label>Agent</Label>
          <Select value={config.agentName || DIRECT_AGENT_VALUE} onValueChange={handleAgentChange}>
            <SelectTrigger>
              <SelectValue placeholder="Select agent" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DIRECT_AGENT_VALUE}>Direct (no agent)</SelectItem>
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
            value={config.provider}
            onValueChange={(v) => update({ provider: v, model: '' })}
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
          <Select value={config.model} onValueChange={(v) => update({ model: v })} disabled={!config.provider}>
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

      <div className="flex min-h-0 flex-1 flex-col gap-2">
        <div className="flex items-center justify-between">
          <Label>Prompt</Label>
          {onGenerate && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onGenerate}
              disabled={generating || !config.prompt.trim()}
              className="h-7 gap-1.5 text-xs"
            >
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              Generate
            </Button>
          )}
        </div>
        <div className="min-h-0 flex-1">
          <InstructionsTextarea
            value={config.prompt}
            onChange={(value) => update({ prompt: value })}
            placeholder="Type a prompt to send to the agent..."
            className="h-full min-h-[180px] resize-none font-mono"
            showExpand
            showOptimize={false}
          />
        </div>
      </div>

      {showEvaluate && (
        <div className="space-y-2">
          <Label>Evaluation criteria</Label>
          <Textarea
            value={config.evaluationCriteria}
            onChange={(e) => update({ evaluationCriteria: e.target.value })}
            placeholder="Describe what a good response must include..."
            className="min-h-[80px] resize-none"
          />
        </div>
      )}

      <div className="flex items-center gap-2 pt-2">
        <Button
          onClick={onRun}
          disabled={
            running ||
            !config.prompt.trim() ||
            !(config.agentName || (config.provider && config.model))
          }
          className="gap-2"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Run
        </Button>
        {showEvaluate && onEvaluate && (
          <Button
            variant="secondary"
            onClick={onEvaluate}
            disabled={evaluating || !config.evaluationCriteria.trim()}
            className="gap-2"
          >
            {evaluating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ShieldCheck className="h-4 w-4" />
            )}
            Evaluate
          </Button>
        )}
      </div>
    </div>
  );
}
