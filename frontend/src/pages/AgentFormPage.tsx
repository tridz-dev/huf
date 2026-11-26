import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useBlocker, useLocation, useNavigate, useParams, type Location } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Lock } from 'lucide-react';
import { toast } from 'sonner';
import { Form } from '@/components/ui/form';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AutosaveStatus, BuilderLayout, ErrorSummary, FormSection, focusFirstError } from '@/components/builder';
import { Button } from '@/components/ui/button';
import { AttentionBanner, DangerZone } from '@/components/patterns';
import { usePermissions } from '@/contexts/PermissionsContext';
import { createAgent, duplicateAgent } from '@/services/agentApi';
import { getWorkspaceDefaultModel } from '@/services/agentForm/agentFormApi';
import type { DraftOverrides } from '@/services/agentForm/agentFormApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { writeToolDetailsSetting } from '@/components/chat/useChatAgentIdentity';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';
import { UnsavedChangesDialog } from '@/components/UnsavedChangesDialog';
import type { AgentDoc } from '@/types/agent.types';
import { AgentHeader } from '@/components/agent/AgentHeader';
import { agentFormSchema, type AgentFormValues } from '@/components/agent/types';
import { SetupTab, type WorkspaceDefaultModel } from '@/components/agent/tabs/SetupTab';
import { AbilitiesTab, type KnowledgeStatus } from '@/components/agent/tabs/AbilitiesTab';
import { ChannelsTab } from '@/components/agent/tabs/ChannelsTab';
import { AdvancedPresetsTab } from '@/components/agent/tabs/AdvancedPresetsTab';
import { AgentCreateCard, type AgentCreateValues } from '@/components/agent/create/AgentCreateCard';
import { AgentTryPanel } from '@/components/agent/try/AgentTryPanel';
import { DeleteAgentFlow } from '@/components/agent/delete/DeleteAgentFlow';
import { ProcedureBindingsTab } from '@/components/agent/ProcedureBindingsTab';
import { useAttachableSources } from '@/components/agent/knowledge/useAttachableSources';
import { AccessTabContainer } from '@/components/agent/form/AccessTabContainer';
import { ProviderModelDialogs } from '@/components/agent/form/ProviderModelDialogs';
import { DEFAULT_FORM_VALUES, TABS, formValuesToDoc, resolveTab, tabForField, type TabKey } from '@/components/agent/form/agentFormModel';
import { useAgentAbilities } from '@/components/agent/form/useAgentAbilities';
import { useAgentOptions } from '@/components/agent/form/useAgentOptions';
import { useAgentSections } from '@/components/agent/form/useAgentSections';
import { useAgentFormEffects } from '@/components/agent/form/useAgentFormEffects';

const DEFAULT_TAB: TabKey = 'setup';
const tabFromHash = (): TabKey => resolveTab(window.location.hash.slice(1)) ?? DEFAULT_TAB;

const conflictLabel = (f: string) => {
  const t = f.replace(/_/g, ' ');
  return t.charAt(0).toUpperCase() + t.slice(1);
};

export function AgentFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const isNew = id === 'new';
  const agentId = !isNew ? id : undefined;
  const { hufRole, hasCapability } = usePermissions();
  const isAdmin = hufRole === 'Huf Admin'; // Backend maps Administrator / System Manager to "Huf Admin".
  // Mirrors the backend's Agent.has_permission() capability checks so the UI never offers what the server rejects.
  const canManage = hasCapability(isNew ? 'agent.create' : 'agent.edit');
  const skipBlockRef = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);

  const form = useForm<AgentFormValues>({ resolver: zodResolver(agentFormSchema), defaultValues: DEFAULT_FORM_VALUES });
  const values = form.watch();
  const modality = values.agent_modality;
  const isVoiceOnly = modality === 'Voice';

  const [activeTab, setActiveTabState] = useState<TabKey>(tabFromHash);
  const setActiveTab = useCallback((tab: TabKey) => {
    setActiveTabState(tab);
    if (tab === DEFAULT_TAB) window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search);
    else window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}#${tab}`);
  }, []);
  useEffect(() => {
    const onHash = () => setActiveTabState(tabFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const options = useAgentOptions(values.provider, values.model, !!values.enable_prompt_caching);
  const abilities = useAgentAbilities({ agentId, navigate: (to) => navigate(to) });
  const sections = useAgentSections({
    id, isNew, form, abilities, canSave: canManage,
    onRenamed: (name) => { skipBlockRef.current = true; navigate(`/agents/${encodeURIComponent(name)}`, { replace: true }); },
    onTabWithError: (tab) => { setActiveTab(tab); requestAnimationFrame(() => focusFirstError(formRef.current)); },
  });
  useAgentFormEffects({ form, location, navigate, activeTab, setActiveTab, abilities, options });

  const systemLocked = sections.isSystem && !isAdmin; // System agents: protected fields are read-only for non-admins.
  const locked = systemLocked || !canManage;

  // Leave guard: in-app navigation (the window-level guard lives in useAgentSections).
  const blocker = useBlocker(useCallback(({ currentLocation, nextLocation }: { currentLocation: Location; nextLocation: Location }) => {
    if (skipBlockRef.current) { skipBlockRef.current = false; return false; }
    return sections.hasUnsaved && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search);
  }, [sections.hasUnsaved]));
  useSaveShortcut({ onSave: sections.saveNow, enabled: canManage && !isNew && sections.hasUnsaved, isSubmitting: sections.status === 'saving' });

  // Workspace default model (recommended); tolerate a backend that does not have the endpoint yet.
  const [defaultModel, setDefaultModel] = useState<{ provider: string | null; model: string | null }>({ provider: null, model: null });
  useEffect(() => { getWorkspaceDefaultModel().then(setDefaultModel).catch(() => undefined); }, []);
  const workspaceDefaultModel: WorkspaceDefaultModel | undefined = defaultModel.provider && defaultModel.model
    ? { provider: defaultModel.provider, model: defaultModel.model, label: options.allModels.find((m) => m.name === defaultModel.model)?.model_name || defaultModel.model }
    : undefined;

  // Knowledge status lines from the Knowledge Source health model.
  const attachable = useAttachableSources(abilities.knowledge.length > 0);
  const knowledgeStatus = useMemo(() => {
    const out: Record<string, KnowledgeStatus> = {};
    for (const s of attachable.sources) {
      if (s.health === 'ready') out[s.name] = { state: 'ready' };
      else if (s.health === 'broken' || s.health === 'attention') out[s.name] = { state: 'failed' };
      else if (s.health === 'empty') out[s.name] = { state: 'empty' };
    }
    return out;
  }, [attachable.sources]);

  const [dialog, setDialog] = useState<'provider' | 'model' | null>(null);
  const [showDelete, setShowDelete] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string>();

  // ---- create ----
  const handleCreate = async (v: AgentCreateValues) => {
    setCreating(true); setCreateError(undefined);
    try {
      const doc = formValuesToDoc({ ...DEFAULT_FORM_VALUES, agent_name: v.agent_name, instructions: v.instructions, provider: v.provider ?? '', model: v.model ?? '', agent_modality: 'Both' });
      const created = await createAgent({ ...doc, agent_tool: [], agent_mcp_server: [], agent_knowledge: [], agent_skill: [] } as unknown as Partial<AgentDoc>);
      writeToolDetailsSetting(created.name, created.show_tool_execution_details === 1);
      navigate(`/agents/${encodeURIComponent(created.name)}`);
    } catch (error) {
      const message = getFrappeErrorMessage(error) || 'Failed to create agent. Please try again.';
      setCreateError(message); toast.error(message);
    } finally { setCreating(false); }
  };

  const handleDuplicate = async () => {
    if (!agentId) return;
    setDuplicating(true);
    try { const copy = await duplicateAgent(agentId); toast.success('Agent duplicated'); navigate(`/agents/${encodeURIComponent(copy.name)}`); }
    catch (error) { toast.error(getFrappeErrorMessage(error) || 'Failed to duplicate agent'); }
    finally { setDuplicating(false); }
  };

  // Create flows on other pages hand their result back through router state (see useAgentFormEffects).
  const goCreate = (path: string, key: string, selectedField: string, showTab: TabKey) => {
    const returnTo = `${location.pathname}#${showTab}`;
    try { localStorage.setItem(key, JSON.stringify({ returnTo, selectedField })); } catch { /* storage may be blocked */ }
    navigate(path, { state: { returnTo, selectedField, showTab } });
  };
  const goCreatePrompt = () => goCreate('/summary-prompts/new', 'agentSummaryPromptCreateReturnTo', 'summary_prompt_template', 'advanced');

  const selectError = (fieldId: string) => {
    setActiveTab(tabForField(fieldId.split('.')[0]));
    requestAnimationFrame(() => focusFirstError(formRef.current));
  };

  const getDraftOverrides = useCallback((): DraftOverrides => {
    const v = form.getValues();
    return {
      ...(v.prompt_mode === 'Local' ? { instructions: v.instructions } : {}),
      provider: v.provider || undefined, model: v.model || undefined, temperature: v.temperature, top_p: v.top_p,
      agent_tool: abilities.tools.map((t) => t.name),
    };
  }, [form, abilities.tools]);

  // ---- render ----
  if (isNew) {
    return (
      <div className="h-full overflow-auto">
        <div className="mx-auto max-w-2xl space-y-4 p-6">
          {!canManage ? (
            <Alert><Lock className="h-4 w-4" /><AlertTitle>Read-only</AlertTitle>
              <AlertDescription>You don't have permission to create agents. Contact a Huf Admin or Manager for access.</AlertDescription></Alert>
          ) : <AgentCreateCard onCreate={handleCreate} busy={creating} error={createError} onCancel={() => navigate('/agents')} />}
        </div>
      </div>
    );
  }

  if (sections.loading) {
    return <div className="flex h-full items-center justify-center"><div className="font-body text-steel-soft">Loading agent...</div></div>;
  }

  const modelName = options.allModels.find((m) => m.name === values.model)?.model_name || values.model;
  const starters = (values.starter_prompts ?? []).map((s) => s.prompt_text?.trim()).filter(Boolean) as string[];
  const title = values.agent_name || agentId || 'Agent';

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-[1400px] space-y-5 p-6">
        {sections.isSystem && (
          <Alert><Lock className="h-4 w-4" /><AlertTitle>System agent — locked</AlertTitle>
            <AlertDescription>{systemLocked
              ? 'This is a protected system agent. Instructions, prompt, provider, model, tools, disabled and chat settings are read-only for your role. Contact a Huf Admin to change them.'
              : 'This is a protected system agent. As a Huf Admin you have full edit access; non-admin users see these fields as read-only.'}</AlertDescription></Alert>
        )}
        {!canManage && (
          <Alert><Lock className="h-4 w-4" /><AlertTitle>Read-only</AlertTitle>
            <AlertDescription>You don't have permission to edit this agent. You can use it, but changes won't be saved.</AlertDescription></Alert>
        )}

        <BuilderLayout asideLabel="Try it" asideSize="lg" aside={
          <AgentTryPanel agentName={agentId} getDraftOverrides={getDraftOverrides} starters={starters} modelLabel={modelName ? `Model: ${modelName}` : undefined}
            badge={values.disabled ? 'Draft · not published' : 'Published'}
            renderBanner={(last) => last && !last.errored && last.toolNames.length === 0 && abilities.tools.length > 0 ? (
              <AttentionBanner message="That answer did not use any of its actions." action={{ label: 'Fix in Abilities', onClick: () => setActiveTab('abilities') }} />
            ) : null} />
        }>
          <AgentHeader
            title={title} disabled={!!values.disabled} modelLabel={isVoiceOnly ? undefined : modelName || 'Model'}
            isSystem={sections.isSystem} locked={locked}
            autosave={<span className="inline-flex items-center gap-2">
              <AutosaveStatus state={sections.status} savedAt={sections.savedAt} onRetry={sections.conflictFields.length || sections.errors.length ? undefined : sections.retry} errorText={sections.errorText} />
              {sections.status === 'error' && canManage && sections.errors.length === 0 && (
                <Button type="button" variant="link" size="sm" onClick={() => void sections.reloadLatest()}>Reload latest</Button>
              )}
            </span>}
            showSave={canManage && (sections.status === 'dirty' || sections.status === 'error')} saving={sections.status === 'saving'} onSave={sections.saveNow}
            onTogglePublish={() => { form.setValue('disabled', !values.disabled, { shouldDirty: true }); void sections.saveNow(); }}
            onDuplicate={handleDuplicate} duplicating={duplicating} onViewLogs={() => navigate(`/executions?agents=${encodeURIComponent(agentId!)}`)}
            onDelete={() => setShowDelete(true)} agentId={agentId!} allowChat={sections.persistedAllowChat}
            lastRun={sections.lastRun} totalRun={sections.totalRun} />

          {sections.conflictFields.length > 0 && (
            <div data-testid="conflict-resolver">
              <AttentionBanner
                message={`Someone else changed: ${sections.conflictFields.map(conflictLabel).join(', ')}. Keep yours or use theirs.`}
                action={{ label: sections.conflictFields.length > 1 ? 'Use theirs (all)' : 'Use theirs', onClick: () => sections.resolveAllConflicts('theirs') }}
                secondary={{ label: sections.conflictFields.length > 1 ? 'Keep mine (all)' : 'Keep mine', onClick: () => sections.resolveAllConflicts('mine') }}
              />
              {sections.conflictFields.length > 1 && <ul className="divide-y divide-line border-b border-line px-4 text-ui-text">
                {sections.conflictFields.map((f) => (
                  <li key={f} className="flex items-center gap-2 py-1.5">
                    <span className="flex-1">{conflictLabel(f)}</span>
                    <Button type="button" variant="outline" size="sm" onClick={() => sections.resolveConflict(f, 'mine')}>Keep mine</Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => sections.resolveConflict(f, 'theirs')}>Use theirs</Button>
                  </li>
                ))}
              </ul>}
              <Button type="button" variant="link" size="sm" onClick={() => void sections.reloadLatest()}>Reload latest</Button>
            </div>
          )}

          <ErrorSummary errors={sections.errors} onSelect={selectError} />

          <Form {...form}>
            <form ref={formRef} onSubmit={(e) => { e.preventDefault(); void sections.saveNow(); }}>
              <Tabs value={activeTab} onValueChange={(t) => setActiveTab(t as TabKey)} className="w-full">
                <TabsList layout="overflow" className="w-full">
                  {TABS.map((t) => <TabsTrigger key={t.key} value={t.key} className="shrink-0">{t.label}</TabsTrigger>)}
                </TabsList>

                <TabsContent value="setup" className="mt-5">
                  <SetupTab form={form} providers={options.providers} models={options.allModels} workspaceDefaultModel={workspaceDefaultModel}
                    promptOptions={options.promptOptions} loadingPrompts={options.loadingPrompts} locked={systemLocked}
                    onAddProvider={() => setDialog('provider')} onAddModel={() => setDialog('model')} />
                </TabsContent>

                <TabsContent value="abilities" className="mt-5">
                  {isVoiceOnly ? (
                    <FormSection title="Procedures" description="Voice-only agents do not use tools, knowledge or skills. Procedures still apply.">
                      <ProcedureBindingsTab agentId={agentId} />
                    </FormSection>
                  ) : (
                    <AbilitiesTab {...abilities.tabProps} knowledgeStatus={knowledgeStatus} locked={systemLocked}
                      skillOptions={options.skillOptions} agentId={agentId} />
                  )}
                </TabsContent>

                <TabsContent value="channels" className="mt-5">
                  <ChannelsTab form={form} allModels={options.allModels} agentId={agentId} locked={systemLocked} />
                </TabsContent>

                <TabsContent value="access" className="mt-5">
                  <AccessTabContainer form={form} owner={sections.owner} locked={locked}
                    executionProfileOptions={options.executionProfileOptions} loadingExecutionProfiles={options.loadingExecutionProfiles}
                    sshConnectionOptions={options.sshConnectionOptions} loadingSSHConnections={options.loadingSSHConnections}
                    desktopAccessStatus={sections.desktopAccessStatus}
                    onCreateExecutionProfile={() => goCreate('/execution-profiles/new', 'executionProfileCreateReturnTo', 'execution_profile', 'access')}
                    onCreateSSHConnection={() => goCreate('/ssh-connections/new', 'sshConnectionCreateReturnTo', 'ssh_connections', 'access')} />
                </TabsContent>

                <TabsContent value="advanced" className="mt-5">
                  <AdvancedPresetsTab form={form} allModels={options.allModels} summaryPromptOptions={options.summaryPromptOptions}
                    loadingSummaryPrompts={options.loadingSummaryPrompts} memoryPolicyOptions={options.memoryPolicyOptions}
                    loadingMemoryPolicies={options.loadingMemoryPolicies} cacheStatus={options.cacheStatus} onCreateSummaryPrompt={goCreatePrompt}
                    locked={locked}
                    dangerZone={<DangerZone title="Delete this agent" description="Check what depends on it first. If it has history, you can disable it instead."
                      actionLabel="Delete or disable…" onAction={() => setShowDelete(true)} />} />
                </TabsContent>
              </Tabs>
            </form>
          </Form>
        </BuilderLayout>
      </div>

      {abilities.modals}
      <ProviderModelDialogs mode={dialog} onClose={() => setDialog(null)} provider={values.provider ?? ''}
        onProviderCreated={async (name) => { await options.reloadProviders(); form.setValue('provider', name, { shouldDirty: true }); form.setValue('model', '', { shouldDirty: true }); }}
        onModelCreated={async (name) => { await options.reloadModels(); form.setValue('model', name, { shouldDirty: true }); }} />
      {agentId && (
        <DeleteAgentFlow open={showDelete} onOpenChange={setShowDelete} agentName={agentId}
          onDone={(result) => {
            skipBlockRef.current = true;
            if (result === 'deleted') { toast.success('Agent deleted'); navigate('/agents'); }
            else { toast.success('Agent disabled. Its history is kept.'); navigate(0); }
          }} />
      )}
      <UnsavedChangesDialog blocker={blocker} />
    </div>
  );
}
