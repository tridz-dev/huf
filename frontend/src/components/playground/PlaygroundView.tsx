import type { AgentDoc, AIProvider } from '@/types/agent.types';
import { ConfigStrip } from './ConfigStrip';
import { PromptPanel } from './PromptPanel';
import { ResponsePanel } from './ResponsePanel';
import { RunLedger, type RunLedgerProps } from './RunLedger';
import type { PlaygroundConfig, SlotState } from './types';

interface PlaygroundViewProps {
  agents: AgentDoc[];
  providers: AIProvider[];
  config: PlaygroundConfig;
  onConfigChange: (config: PlaygroundConfig) => void;
  slot: SlotState;
  onDraft: () => void;
  ledger: RunLedgerProps;
}

export function PlaygroundView({
  agents,
  providers,
  config,
  onConfigChange,
  slot,
  onDraft,
  ledger,
}: PlaygroundViewProps) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="px-5 pt-[18px]">
        <ConfigStrip agents={agents} providers={providers} config={config} onChange={onConfigChange} />
      </div>

      <div className="grid min-h-[340px] flex-1 grid-cols-1 gap-4 p-5 lg:grid-cols-2">
        <PromptPanel
          config={config}
          onConfigChange={onConfigChange}
          onDraft={onDraft}
          generating={slot.generating}
          className="h-full"
        />
        <ResponsePanel title="Response" state={slot} className="h-full" />
      </div>

      <div className="px-5 pb-[18px]">
        <RunLedger {...ledger} />
      </div>
    </div>
  );
}
