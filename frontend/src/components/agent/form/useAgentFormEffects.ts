/**
 * Form side effects that are not about loading or saving: keep prompt-template fields consistent,
 * and apply what another page handed back through router state (a new knowledge source, MCP server,
 * execution profile, SSH connection or prompt).
 */
import { useEffect, useState } from 'react';
import type { Location, NavigateFunction } from 'react-router-dom';
import { toast } from 'sonner';
import { db } from '@/lib/frappe-sdk';
import { getAgentPrompt } from '@/services/agentPromptApi';
import { getAgentSummaryPrompt } from '@/services/agentSummaryPromptApi';
import type { AgentKnowledgeRow } from '@/types/agent.types';
import type { MCPServerRef } from '@/services/mcpApi';
import type { AgentPromptOption } from '../PromptTemplateSection';
import type { ExecutionProfileOption, SSHConnectionOption } from '../AdvancedTab';
import type { AgentForm } from '../tabs/fields';
import { resolveTab, type TabKey } from './agentFormModel';
import type { useAgentAbilities } from './useAgentAbilities';
import type { useAgentOptions } from './useAgentOptions';

interface NavState {
  selectedPrompt?: string; showTab?: string; selectedPromptField?: string; linkedKnowledge?: AgentKnowledgeRow;
  linkedMcpServer?: MCPServerRef; selectedExecutionProfile?: string; selectedSSHConnection?: string;
}

interface Args {
  form: AgentForm;
  location: Location;
  navigate: NavigateFunction;
  activeTab: TabKey;
  setActiveTab: (tab: TabKey) => void;
  abilities: ReturnType<typeof useAgentAbilities>;
  options: ReturnType<typeof useAgentOptions>;
}

export function useAgentFormEffects({ form, location, navigate, activeTab, setActiveTab, abilities, options }: Args) {
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const [pendingField, setPendingField] = useState<string | null>(null);
  const [scrollToPrompt, setScrollToPrompt] = useState(false);
  const [resolving, setResolving] = useState(false);
  const { promptOptions, summaryPromptOptions, setPromptOptions, setSummaryPromptOptions, setExecutionProfileOptions, setSSHConnectionOptions } = options;

  const mode = form.watch('prompt_mode');
  const agentPrompt = form.watch('agent_prompt');
  const summaryMode = form.watch('summary_prompt_mode');
  const summaryTemplate = form.watch('summary_prompt_template');

  // Router state handed back by create flows on other pages.
  useEffect(() => {
    const state = location.state as NavState | null;
    if (!state) return;
    const back = (tab: TabKey) => { setActiveTab(tab); navigate(`${location.pathname}${location.search}#${tab}`, { replace: true, state: {} }); };
    if (state.linkedKnowledge) { abilities.addLinkedKnowledge(state.linkedKnowledge); back('abilities'); return; }
    if (state.linkedMcpServer) { abilities.addLinkedMcp(state.linkedMcpServer); back('abilities'); return; }
    if (state.selectedExecutionProfile) {
      db.getDoc('Execution Profile', state.selectedExecutionProfile).then((doc: Record<string, string> | null) => {
        if (!doc) return;
        setExecutionProfileOptions((prev: ExecutionProfileOption[]) => prev.some((p) => p.value === doc.name) ? prev
          : [{ value: doc.name, label: doc.profile_name || doc.name, approvalMode: doc.approval_mode }, ...prev]);
        form.setValue('execution_profile', doc.name, { shouldDirty: true });
      }).catch(console.error);
      back('access'); return;
    }
    if (state.selectedSSHConnection) {
      db.getDoc('SSH Connection', state.selectedSSHConnection).then((doc: Record<string, string> | null) => {
        if (!doc) return;
        setSSHConnectionOptions((prev: SSHConnectionOption[]) => prev.some((c) => c.value === doc.name) ? prev
          : [{ value: doc.name, label: doc.display_name || doc.name, description: [doc.username, doc.host].filter(Boolean).join('@') }, ...prev]);
        const current = form.getValues('ssh_connections') || [];
        if (!current.includes(doc.name)) form.setValue('ssh_connections', [...current, doc.name], { shouldDirty: true });
      }).catch(console.error);
      back('access'); return;
    }
    if (state.selectedPrompt) {
      setPendingPrompt(state.selectedPrompt);
      setPendingField(state.selectedPromptField || 'agent_prompt');
      const tab = resolveTab(state.showTab) ?? (state.selectedPromptField === 'summary_prompt_template' ? 'advanced' : 'setup');
      setActiveTab(tab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  // Apply a prompt created on another page.
  useEffect(() => {
    if (!pendingPrompt || resolving) return;
    const field = pendingField || 'agent_prompt';
    let cancelled = false;
    (async () => {
      setResolving(true);
      try {
        const isSummary = field === 'summary_prompt_template';
        const existing = isSummary ? summaryPromptOptions : promptOptions;
        if (!existing.some((o) => o.value === pendingPrompt)) {
          const doc = isSummary ? await getAgentSummaryPrompt(pendingPrompt) : await getAgentPrompt(pendingPrompt);
          if (doc?.is_active === 1) {
            const option: AgentPromptOption = {
              value: doc.name, label: doc.title || doc.name, description: doc.description || undefined,
              version: typeof doc.version === 'number' ? doc.version : undefined, isLatest: doc.is_latest === 1,
            };
            (isSummary ? setSummaryPromptOptions : setPromptOptions)((prev: AgentPromptOption[]) => prev.some((p) => p.value === option.value) ? prev : [option, ...prev]);
          }
        }
        if (field === 'agent_prompt' && form.getValues('prompt_mode') !== 'Template') form.setValue('prompt_mode', 'Template', { shouldDirty: true });
        if (isSummary && form.getValues('summary_prompt_mode') !== 'Template') form.setValue('summary_prompt_mode', 'Template', { shouldDirty: true });
        form.setValue(field as 'agent_prompt' | 'summary_prompt_template', pendingPrompt, { shouldDirty: true });
        setPendingPrompt(null); setPendingField(null); setScrollToPrompt(true);
        navigate(`${location.pathname}${location.search}${location.hash}`, { replace: true, state: {} });
      } catch (error) {
        console.error('Failed to resolve pending prompt selection:', error);
        toast.error('Failed to select newly created prompt');
      } finally {
        if (!cancelled) setResolving(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt, pendingField, resolving, promptOptions, summaryPromptOptions]);

  // Local mode carries no template; an empty template carries no version.
  useEffect(() => {
    if (pendingPrompt) return;
    if (mode === 'Local') {
      form.setValue('agent_prompt', '', { shouldDirty: false });
      form.setValue('prompt_version_locked', false, { shouldDirty: false });
      form.setValue('template_version_at_attach', undefined, { shouldDirty: false });
    } else if (mode === 'Template' && !agentPrompt) {
      form.setValue('prompt_version_locked', false, { shouldDirty: false });
      form.setValue('template_version_at_attach', undefined, { shouldDirty: false });
    }
  }, [mode, agentPrompt, form, pendingPrompt]);

  useEffect(() => {
    if (pendingPrompt) return;
    if (summaryMode === 'Local') {
      form.setValue('summary_prompt_template', '', { shouldDirty: false });
      form.setValue('summary_prompt_version_locked', false, { shouldDirty: false });
      form.setValue('summary_template_version_at_attach', undefined, { shouldDirty: false });
    } else if (summaryMode === 'Template' && !summaryTemplate) {
      form.setValue('summary_prompt_version_locked', false, { shouldDirty: false });
      form.setValue('summary_template_version_at_attach', undefined, { shouldDirty: false });
    }
  }, [summaryMode, summaryTemplate, form, pendingPrompt]);

  // Record the template version the agent was attached at.
  useEffect(() => {
    if (mode !== 'Template' || !agentPrompt) return;
    const v = promptOptions.find((o) => o.value === agentPrompt)?.version;
    if (typeof v === 'number' && form.getValues('template_version_at_attach') !== v) form.setValue('template_version_at_attach', v, { shouldDirty: true });
  }, [mode, agentPrompt, promptOptions, form]);

  useEffect(() => {
    if (summaryMode !== 'Template' || !summaryTemplate) return;
    const v = summaryPromptOptions.find((o) => o.value === summaryTemplate)?.version;
    if (typeof v === 'number' && form.getValues('summary_template_version_at_attach') !== v) form.setValue('summary_template_version_at_attach', v, { shouldDirty: true });
  }, [summaryMode, summaryTemplate, summaryPromptOptions, form]);

  // Scroll the freshly attached template into view.
  useEffect(() => {
    if (!scrollToPrompt) return;
    const el = activeTab === 'setup' && mode === 'Template' ? document.getElementById('agent-prompt-field')
      : activeTab === 'advanced' && summaryMode === 'Template' ? document.getElementById('summary-prompt-template-field') : null;
    if (el) requestAnimationFrame(() => requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'center' })));
    setScrollToPrompt(false);
  }, [scrollToPrompt, activeTab, mode, summaryMode]);
}
