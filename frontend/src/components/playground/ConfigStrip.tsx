import { useEffect, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { toast } from 'sonner';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getModels, type PaginatedModelsResponse } from '@/services/providerApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { cn } from '@/lib/utils';
import type { AgentDoc, AIModel, AIProvider } from '@/types/agent.types';
import type { PlaygroundConfig } from './types';

const DIRECT_AGENT_VALUE = '__direct__';

interface ConfigStripProps {
  agents: AgentDoc[];
  providers: AIProvider[];
  config: PlaygroundConfig;
  onChange: (config: PlaygroundConfig) => void;
  /** Compact = 2×2 grid per compare column; default = one 4-column strip. */
  compact?: boolean;
}

/** One labelled cell of the playground config strip; also reused by the Decision tab. */
export function ConfigStripCell({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  /** Optional one-line explanation, shown as the label's native tooltip. */
  hint?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn('min-w-0 px-4 py-3', className)}>
      {/* Plain concatenation, not cn(): tailwind-merge reads the custom text-eyebrow size
          as a colour and drops it in favour of text-steel-soft. */}
      <div
        className={`mb-1.5 font-mono text-eyebrow uppercase text-steel-soft${hint ? ' cursor-help underline decoration-dotted decoration-line underline-offset-2' : ''}`}
        title={hint}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

/** Select trigger restyled to sit flush inside a strip cell (no box of its own). */
export const flushTriggerClass =
  'h-auto w-auto justify-start gap-2 rounded-none border-0 bg-transparent px-0 py-0 text-[13.5px] text-ink shadow-none focus:ring-0 focus:ring-offset-0 disabled:opacity-40 [&>span]:truncate';

export function ConfigStrip({ agents, providers, config, onChange, compact }: ConfigStripProps) {
  const [models, setModels] = useState<AIModel[]>([]);

  useEffect(() => {
    if (!config.provider) {
      setModels([]);
      return;
    }
    let cancelled = false;
    getModels({ provider: config.provider, modality: 'Text' })
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

  const update = (patch: Partial<PlaygroundConfig>) => {
    onChange({ ...config, ...patch });
  };

  const handleAgentChange = (value: string) => {
    if (value === DIRECT_AGENT_VALUE) {
      update({ agentName: '' });
      return;
    }
    // Selecting an agent auto-fills its provider and model.
    const agent = agents.find((a) => a.name === value);
    update({
      agentName: value,
      provider: agent?.provider || '',
      model: agent?.model || '',
    });
  };

  const agentControl = (
    <Select value={config.agentName || DIRECT_AGENT_VALUE} onValueChange={handleAgentChange}>
      <SelectTrigger
        className={flushTriggerClass}
        icon={<ChevronDown className="h-3.5 w-3.5 text-steel" strokeWidth={1.8} />}
      >
        <SelectValue placeholder="Direct (no agent)" />
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
  );

  const providerControl = (
    <Select value={config.provider} onValueChange={(v) => update({ provider: v, model: '' })}>
      <SelectTrigger
        className={flushTriggerClass}
        icon={<ChevronDown className="h-3.5 w-3.5 text-steel" strokeWidth={1.8} />}
      >
        <SelectValue placeholder="Select provider" />
      </SelectTrigger>
      <SelectContent>
        {providers.map((p) => (
          <SelectItem key={p.name} value={p.name}>
            {p.provider_name || p.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const modelControl = (
    <Select
      value={config.model}
      onValueChange={(v) => update({ model: v })}
      disabled={!config.provider}
    >
      <SelectTrigger
        className={cn(flushTriggerClass, 'font-mono text-[12.5px]')}
        icon={<ChevronDown className="h-3.5 w-3.5 text-steel" strokeWidth={1.8} />}
      >
        <SelectValue placeholder={config.provider ? 'Select model' : 'Pick a provider first'} />
      </SelectTrigger>
      <SelectContent>
        {models.map((m) => (
          <SelectItem key={m.name} value={m.name}>
            {m.model_name || m.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const generationControl = (
    <div className="flex items-center gap-1.5 font-mono text-[12.5px] text-ink">
      <input
        value={config.temperature}
        onChange={(e) => update({ temperature: e.target.value })}
        placeholder="0.70"
        inputMode="decimal"
        aria-label="Temperature"
        className="w-12 bg-transparent outline-none placeholder:text-steel-soft"
      />
      <span className="text-steel-soft">·</span>
      <input
        value={config.maxTokens}
        onChange={(e) => update({ maxTokens: e.target.value })}
        placeholder="4096"
        inputMode="numeric"
        aria-label="Max tokens"
        className="w-14 bg-transparent outline-none placeholder:text-steel-soft"
      />
    </div>
  );

  if (compact) {
    return (
      <div className="grid grid-cols-2 rounded border border-line bg-panel [&>div]:px-3.5 [&>div]:py-2.5">
        <ConfigStripCell label="Provider" className="border-b border-r border-line">
          {providerControl}
        </ConfigStripCell>
        <ConfigStripCell label="Model" className="border-b border-line">
          {modelControl}
        </ConfigStripCell>
        <ConfigStripCell label="Agent" className="border-r border-line">
          {agentControl}
        </ConfigStripCell>
        <ConfigStripCell label="Temp · max tok">{generationControl}</ConfigStripCell>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-4 rounded border border-line bg-panel max-lg:grid-cols-2">
      <ConfigStripCell label="Agent" className="border-r border-line max-lg:border-b">
        {agentControl}
      </ConfigStripCell>
      <ConfigStripCell label="Provider" className="border-r border-line max-lg:border-b max-lg:border-r-0">
        {providerControl}
      </ConfigStripCell>
      <ConfigStripCell label="Model" className="border-r border-line">
        {modelControl}
      </ConfigStripCell>
      <ConfigStripCell label="Temp · max tok">{generationControl}</ConfigStripCell>
    </div>
  );
}
