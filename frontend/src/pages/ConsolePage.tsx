import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { useSidebar } from '@/components/ui/sidebar';
import {
  ConsoleHeader,
  ConsolePlayground,
  ConsoleCompare,
  ConsoleTemplates,
  SaveTemplateDialog,
  type ConsoleMode,
  type ConsoleConfig,
} from '@/components/console';
import { getAgents } from '@/services/agentApi';
import { getProviders } from '@/services/providerApi';
import { settleAll } from '@/lib/settleAll';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AgentDoc, AIProvider } from '@/types/agent.types';
import type { AgentPromptDoc } from '@/services/agentPromptApi';

export { ConsolePage };
export default ConsolePage;

function emptyConfig(): ConsoleConfig {
  return {
    agentName: '',
    provider: '',
    model: '',
    prompt: '',
    evaluationCriteria: '',
  };
}

function ConsolePage() {
  const { setOpen } = useSidebar();
  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<AgentDoc[]>([]);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [mode, setMode] = useState<ConsoleMode>('playground');
  const [playgroundConfig, setPlaygroundConfig] = useState<ConsoleConfig>(emptyConfig());
  const [compareConfigA, setCompareConfigA] = useState<ConsoleConfig>(emptyConfig());
  const [compareConfigB, setCompareConfigB] = useState<ConsoleConfig>(emptyConfig());
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);

  // Close the global app sidebar so the console uses the full viewport width.
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

  const activePromptBody = () => {
    if (mode === 'playground') return playgroundConfig.prompt;
    if (mode === 'compare') return compareConfigA.prompt || compareConfigB.prompt;
    return '';
  };

  const handleLoadTemplate = (prompt: AgentPromptDoc) => {
    if (mode === 'compare') {
      setCompareConfigA((prev) => ({ ...prev, prompt: prompt.prompt_body }));
      setCompareConfigB((prev) => ({ ...prev, prompt: prompt.prompt_body }));
    } else {
      setPlaygroundConfig((prev) => ({ ...prev, prompt: prompt.prompt_body }));
      // Switch to playground so the user can immediately run the loaded template.
      setMode('playground');
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <ConsoleHeader
        mode={mode}
        onModeChange={setMode}
        onSaveTemplate={() => setSaveDialogOpen(true)}
        onLoadTemplate={handleLoadTemplate}
        canSave={!!activePromptBody().trim()}
      />

      <main className="min-h-0 flex-1 overflow-hidden">
        {mode === 'playground' && (
          <ConsolePlayground
            agents={agents}
            providers={providers}
            config={playgroundConfig}
            onConfigChange={setPlaygroundConfig}
          />
        )}
        {mode === 'compare' && (
          <ConsoleCompare
            agents={agents}
            providers={providers}
            configA={compareConfigA}
            configB={compareConfigB}
            onConfigAChange={setCompareConfigA}
            onConfigBChange={setCompareConfigB}
          />
        )}
        {mode === 'templates' && (
          <ConsoleTemplates onLoadTemplate={handleLoadTemplate} />
        )}
      </main>

      <SaveTemplateDialog
        open={saveDialogOpen}
        onOpenChange={setSaveDialogOpen}
        promptBody={activePromptBody()}
      />
    </div>
  );
}
