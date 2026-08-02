import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { useSidebar } from '@/components/ui/sidebar';
import {
  CompareView,
  PlaygroundShell,
  PlaygroundView,
  SaveTemplateDialog,
  TemplatePickerDialog,
  emptyPlaygroundConfig,
  loadLedgerEntries,
  saveLedgerEntries,
  usePlaygroundSlot,
  type LedgerEntry,
  type PlaygroundConfig,
  type PlaygroundMode,
  type RunOutcome,
} from '@/components/playground';
import { getAgents } from '@/services/agentApi';
import { getProviders } from '@/services/providerApi';
import { settleAll } from '@/lib/settleAll';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AgentDoc, AIProvider } from '@/types/agent.types';
import type { AgentPromptDoc } from '@/services/agentPromptApi';

export { PlaygroundPage };
export default PlaygroundPage;

function PlaygroundPage() {
  const { setOpen } = useSidebar();
  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<AgentDoc[]>([]);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [mode, setMode] = useState<PlaygroundMode>('playground');
  const [playgroundConfig, setPlaygroundConfig] = useState<PlaygroundConfig>(emptyPlaygroundConfig());
  const [compareConfigA, setCompareConfigA] = useState<PlaygroundConfig>(emptyPlaygroundConfig());
  const [compareConfigB, setCompareConfigB] = useState<PlaygroundConfig>(emptyPlaygroundConfig());
  const [ledgerEntries, setLedgerEntries] = useState<LedgerEntry[]>(() => loadLedgerEntries());
  const [latestEntryId, setLatestEntryId] = useState<string>();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [savePromptOverride, setSavePromptOverride] = useState<string | null>(null);

  // Close the global app sidebar so the playground uses the full viewport width.
  useEffect(() => {
    setOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      if (providersRes)
        setProviders(Array.isArray(providersRes) ? providersRes : providersRes.items);
      setLoading(false);
    })();
  }, []);

  const recordRun = useCallback((config: PlaygroundConfig, outcome: RunOutcome) => {
    const tokens =
      outcome.inputTokens !== undefined || outcome.outputTokens !== undefined
        ? (outcome.inputTokens ?? 0) + (outcome.outputTokens ?? 0)
        : undefined;
    const entry: LedgerEntry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      ranAt: Date.now(),
      status: outcome.success ? 'ok' : 'held',
      model: outcome.model || config.model,
      latencyMs: outcome.latencyMs,
      tokens,
      config: { ...config },
    };
    setLedgerEntries((prev) => {
      const next = [entry, ...prev].slice(0, 50);
      saveLedgerEntries(next);
      return next;
    });
    setLatestEntryId(entry.id);
  }, []);

  const playgroundSlot = usePlaygroundSlot(playgroundConfig, setPlaygroundConfig, recordRun);
  const compareSlotA = usePlaygroundSlot(compareConfigA, setCompareConfigA, recordRun);
  const compareSlotB = usePlaygroundSlot(compareConfigB, setCompareConfigB, recordRun);

  const activePromptBody = () => {
    if (mode === 'compare') return compareConfigA.prompt || compareConfigB.prompt;
    return playgroundConfig.prompt;
  };

  const handleLoadTemplate = (prompt: AgentPromptDoc) => {
    if (mode === 'compare') {
      setCompareConfigA((prev) => ({ ...prev, prompt: prompt.prompt_body }));
      setCompareConfigB((prev) => ({ ...prev, prompt: prompt.prompt_body }));
    } else {
      setPlaygroundConfig((prev) => ({ ...prev, prompt: prompt.prompt_body }));
    }
  };

  const handleRestore = (entry: LedgerEntry) => {
    if (mode === 'compare') {
      // In compare, a restored run lands in column A.
      setCompareConfigA({ ...entry.config });
    } else {
      setPlaygroundConfig({ ...entry.config });
    }
    toast.success('Restored run into the bench');
  };

  const handleSaveEntryAsTemplate = (entry: LedgerEntry) => {
    if (!entry.config.prompt.trim()) {
      toast.error('That run has no prompt to save');
      return;
    }
    setSavePromptOverride(entry.config.prompt);
    setSaveDialogOpen(true);
  };

  const handleSaveCurrent = () => {
    setSavePromptOverride(null);
    setSaveDialogOpen(true);
  };

  const handleRunPrimary = () => {
    if (mode === 'compare') {
      compareSlotA.run();
      compareSlotB.run();
    } else {
      playgroundSlot.run();
    }
  };

  const primaryRunning =
    mode === 'compare'
      ? compareSlotA.state.running || compareSlotB.state.running
      : playgroundSlot.state.running;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-paper">
        <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
      </div>
    );
  }

  const ledgerProps = {
    entries: ledgerEntries,
    latestEntryId,
    onRestore: handleRestore,
    onSaveAsTemplate: handleSaveEntryAsTemplate,
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-paper text-ink">
      <PlaygroundShell
        mode={mode}
        onModeChange={setMode}
        onRun={handleRunPrimary}
        running={primaryRunning}
        canSaveTemplate={!!activePromptBody().trim()}
        onLoadTemplate={() => setPickerOpen(true)}
        onSaveTemplate={handleSaveCurrent}
      />

      <main className="min-h-0 flex-1 overflow-hidden">
        {mode === 'playground' ? (
          <PlaygroundView
            agents={agents}
            providers={providers}
            config={playgroundConfig}
            onConfigChange={setPlaygroundConfig}
            slot={playgroundSlot.state}
            onDraft={playgroundSlot.draft}
            ledger={ledgerProps}
          />
        ) : (
          <CompareView
            agents={agents}
            providers={providers}
            configA={compareConfigA}
            configB={compareConfigB}
            onConfigAChange={setCompareConfigA}
            onConfigBChange={setCompareConfigB}
            slotA={compareSlotA.state}
            slotB={compareSlotB.state}
            onRunA={compareSlotA.run}
            onRunB={compareSlotB.run}
            onDraftA={compareSlotA.draft}
            onDraftB={compareSlotB.draft}
            ledger={ledgerProps}
          />
        )}
      </main>

      <TemplatePickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onLoadTemplate={handleLoadTemplate}
      />
      <SaveTemplateDialog
        open={saveDialogOpen}
        onOpenChange={(open) => {
          setSaveDialogOpen(open);
          if (!open) setSavePromptOverride(null);
        }}
        promptBody={savePromptOverride ?? activePromptBody()}
      />
    </div>
  );
}
