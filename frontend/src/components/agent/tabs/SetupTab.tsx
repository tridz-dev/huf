/**
 * SetupTab: Instructions, Basics, Model. Replaces GeneralTab's identity / prompt / LLM cards.
 * Controlled by the page's react-hook-form (AgentFormValues); no data fetching.
 *
 * Field mapping (constraints.md (a)+(b), General tab):
 *   agent_modality ........ Basics (PresetSelector Text / Voice / Both; sets voice_enabled as GeneralTab did)
 *   agent_name ............ Basics, required, inline error
 *   description ........... Basics
 *   starter_prompts ....... Basics, max 3, prompt_text required (hidden Voice-only)
 *   prompt_mode ........... Instructions (Local / Template)
 *   instructions .......... Instructions (Local), required inline error
 *   agent_prompt .......... Instructions (Template) via PromptTemplateSection
 *   prompt_version_locked, template_version_at_attach ... PromptTemplateSection (unchanged)
 *   provider, model ....... Model: recommended line + Change; model list filtered to chat models
 *                           (isChatModel: Text/Vision/none recorded) and to the provider; hidden Voice-only
 * Moved to AdvancedPresetsTab (Advanced): temperature, top_p, run_immediately, prompt_cache_mode,
 *   enable_prompt_caching, cache_control_type, cache_system_message, cache_conversation_history.
 * Moved to channels (not this track): allow_chat (BehaviorTab). disabled stays in the page header.
 */
import { useEffect, useState } from 'react';
import { useFieldArray } from 'react-hook-form';
import { Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';
import { Form } from '@/components/ui/form';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { FormSection, FieldError, PresetSelector, RequiredMark } from '@/components/builder';
import { AttentionBanner } from '@/components/patterns';
import { Label } from '@/components/ui/label';
import { isChatModel } from '@/lib/chatModel';
import type { AIModel, AIProvider } from '@/types/agent.types';
import { InstructionsTextarea } from '../InstructionsTextarea';
import { PromptTemplateSection, type AgentPromptOption } from '../PromptTemplateSection';
import { useFormBinding, type AgentForm } from './fields';

export interface WorkspaceDefaultModel {
  provider: string;
  model: string;
  /** Human label, e.g. "Gemini Flash". */
  label: string;
}

export interface SetupTabProps {
  form: AgentForm;
  providers: AIProvider[];
  /** All models; the tab filters to the chosen provider and to chat-capable ones. */
  models: AIModel[];
  /** Recommended workspace default, shown as "<label> (recommended)". */
  workspaceDefaultModel?: WorkspaceDefaultModel;
  /** When true (new agents) an empty provider/model is filled with the workspace default so no select is blank. */
  applyDefaultWhenEmpty?: boolean;
  promptOptions: AgentPromptOption[];
  loadingPrompts?: boolean;
  showAddNewPrompt?: boolean;
  optimizingPrompt?: boolean;
  onOptimizePrompt?: () => void;
  /** Open the page's "Add provider" / "Add model" dialogs. */
  onAddProvider?: () => void;
  onAddModel?: () => void;
  /** System agent + non-admin: protected fields read-only. */
  locked?: boolean;
}

const MODALITY_PRESETS = [
  { value: 'Both', label: 'Text and voice', description: 'Chat and calls' },
  { value: 'Text', label: 'Text only', description: 'Chat only' },
  { value: 'Voice', label: 'Voice only', description: 'Calls only' },
] as const;

export function SetupTab({
  form, providers, models, workspaceDefaultModel, applyDefaultWhenEmpty = false,
  promptOptions, loadingPrompts = false, showAddNewPrompt = true,
  optimizingPrompt = false, onOptimizePrompt, onAddProvider, onAddModel, locked = false,
}: SetupTabProps) {
  const { get, set, error } = useFormBinding(form);
  const modality = get('agent_modality') ?? 'Both';
  const isVoiceOnly = modality === 'Voice';
  const promptMode = get('prompt_mode') ?? 'Local';
  const provider = get('provider') ?? '';
  const model = get('model') ?? '';
  const instructions = get('instructions') ?? '';

  const { fields: starters, append, remove } = useFieldArray({ control: form.control, name: 'starter_prompts' });
  const starterErrors = form.formState.errors.starter_prompts;

  const chatModels = models.filter(isChatModel);
  const providerModels = chatModels.filter((m) => m.provider === provider);
  const selectedModel = models.find((m) => m.name === model);
  const selectedProvider = providers.find((p) => p.name === provider);
  const isDefault = !!workspaceDefaultModel && workspaceDefaultModel.provider === provider && workspaceDefaultModel.model === model;
  // A saved model that is not a chat model (or vanished from the provider) is flagged, never silently dropped.
  const modelUnavailable = !!model && models.length > 0 && (!selectedModel || !isChatModel(selectedModel));

  const [changing, setChanging] = useState(!model && !workspaceDefaultModel);

  useEffect(() => {
    if (applyDefaultWhenEmpty && workspaceDefaultModel && !provider && !model) {
      set('provider', workspaceDefaultModel.provider);
      set('model', workspaceDefaultModel.model);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyDefaultWhenEmpty, workspaceDefaultModel?.provider, workspaceDefaultModel?.model]);

  const useRecommended = () => {
    if (!workspaceDefaultModel) return;
    set('provider', workspaceDefaultModel.provider);
    set('model', workspaceDefaultModel.model);
    setChanging(false);
  };

  const providerOptions: ComboboxOption[] = [
    ...providers.map((p) => ({ value: p.name, label: p.provider_name || p.name })),
    ...(onAddProvider ? [{ value: '__add_provider__', label: '+ Add provider', action: onAddProvider }] : []),
  ];
  const modelOptions: ComboboxOption[] = [
    ...providerModels.map((m) => ({ value: m.name, label: m.model_name || m.name })),
    ...(onAddModel && provider ? [{ value: '__add_model__', label: '+ Add model', action: onAddModel }] : []),
  ];

  const currentLine = model
    ? `${selectedProvider?.provider_name || provider} · ${selectedModel?.model_name || model}`
    : 'No model chosen yet';

  return (
    <div className="space-y-6">
      <FormSection title="Instructions" description="Tell it what to do, who it talks to, and what to avoid. Edit, then press Reset in Try it to test the new version.">
        <PresetSelector label="Where the instructions live" value={promptMode} onChange={(v) => !locked && set('prompt_mode', v as 'Local' | 'Template')}
          presets={[
            { value: 'Local', label: 'Write them here', description: 'Instructions stay with this agent' },
            { value: 'Template', label: 'Use a template', description: 'Link a reusable prompt' },
          ]} />
        {promptMode === 'Local' ? (
          <div>
            <Label htmlFor="instructions">Instructions<RequiredMark /></Label>
            <div id="instructions" tabIndex={-1} aria-invalid={error('instructions') ? true : undefined}
              aria-describedby={error('instructions') ? 'instructions-err' : undefined} className="mt-1.5 outline-none">
              <InstructionsTextarea value={instructions} onChange={(v) => set('instructions', v)}
                optimizingPrompt={optimizingPrompt} onOptimizePrompt={onOptimizePrompt} showOptimize={!!onOptimizePrompt}
                showExpand disabled={locked} className="min-h-[220px] font-mono resize-y" />
            </div>
            <FieldError id="instructions-err">{error('instructions')}</FieldError>
          </div>
        ) : (
          <Form {...form}>
            <PromptTemplateSection form={form} promptOptions={promptOptions} loadingPrompts={loadingPrompts} showAddNew={showAddNewPrompt} locked={locked} />
          </Form>
        )}
      </FormSection>

      <FormSection title="Basics" description="What people see when they pick or open this agent.">
        <Field label="Name" required error={error('agent_name')} hint="A unique name for this agent.">
          <Input autoComplete="off" placeholder="my-agent" {...form.register('agent_name')} />
        </Field>
        <Field label="Description" hint="A short summary of what it is for.">
          <Textarea className="min-h-[72px] resize-y" placeholder="Answers questions about orders and returns." {...form.register('description')} />
        </Field>
        <div>
          <p className="mb-1.5 text-ui-text font-medium text-ink">Works through</p>
          <PresetSelector label="Works through" value={modality} presets={[...MODALITY_PRESETS]}
            onChange={(v) => {
              if (locked) return;
              set('agent_modality', v as 'Text' | 'Voice' | 'Both');
              if (v === 'Text') set('voice_enabled', false);
              else if (v === 'Voice') set('voice_enabled', true);
            }} />
          {isVoiceOnly && <p className="mt-1.5 text-micro text-steel">Voice only hides text-model settings, tools, knowledge and skills.</p>}
        </div>
        {!isVoiceOnly && (
          <div>
            <p className="mb-1.5 text-ui-text font-medium text-ink">Conversation starters</p>
            <p className="mb-2 text-micro text-steel">Up to 3 suggestions shown when someone starts a chat.</p>
            <div className="space-y-2">
              {starters.map((row, i) => {
                const msg = (starterErrors as { message?: string; [k: number]: { prompt_text?: { message?: string } } | undefined } | undefined)?.[i]?.prompt_text?.message;
                return (
                  <div key={row.id} className="flex items-start gap-2">
                    <Field className="flex-1" error={msg}>
                      <Textarea aria-label={`Starter ${i + 1}`} className="min-h-[56px] resize-y" placeholder="e.g. Where is my order?"
                        {...form.register(`starter_prompts.${i}.prompt_text` as const)} />
                    </Field>
                    <Button type="button" variant="ghost" size="icon" aria-label="Remove starter prompt" onClick={() => remove(i)}>
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                );
              })}
              {starters.length < 3 ? (
                <Button type="button" variant="outline" size="sm" onClick={() => append({ prompt_text: '' }, { shouldFocus: true })}>
                  <Plus className="mr-1 h-4 w-4" />Add a starter
                </Button>
              ) : (
                <p className="text-micro text-steel">3 of 3 added.</p>
              )}
              {typeof (starterErrors as { message?: string } | undefined)?.message === 'string' && (
                <FieldError>{(starterErrors as { message?: string }).message}</FieldError>
              )}
            </div>
          </div>
        )}
      </FormSection>

      {!isVoiceOnly && (
        <FormSection title="Model" description="The AI that writes the replies."
          actions={<Button type="button" variant="outline" size="sm" disabled={locked} onClick={() => setChanging((c) => !c)} aria-expanded={changing}>{changing ? 'Done' : 'Change'}</Button>}>
          {modelUnavailable && (
            <AttentionBanner message="This model is not available for chat. Pick another one to keep replies working."
              action={workspaceDefaultModel ? { label: 'Use recommended', onClick: useRecommended } : undefined} />
          )}
          <p data-testid="model-line" className="text-ui-text text-ink">
            {currentLine}
            {isDefault && <span className="ml-1.5 text-meta text-signal-ink">Recommended</span>}
          </p>
          {!model && !changing && (error('model') || error('provider')) && <FieldError>{error('model') || error('provider')}</FieldError>}
          {changing && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Provider" required error={error('provider')}>
                {(p) => (
                  <Combobox id={p.id} options={providerOptions} value={provider} disabled={locked}
                    onValueChange={(v) => { set('provider', v); set('model', ''); }}
                    placeholder="Choose a provider" searchPlaceholder="Search providers..." emptyText="No providers found" />
                )}
              </Field>
              <Field label="Model" required error={error('model')}>
                {(p) => (
                  <Combobox id={p.id} options={modelOptions} value={model} disabled={!provider || locked}
                    onValueChange={(v) => set('model', v)}
                    placeholder={provider ? 'Choose a model' : 'Choose a provider first'} searchPlaceholder="Search models..." emptyText="No chat models for this provider" />
                )}
              </Field>
              {workspaceDefaultModel && !isDefault && (
                <div className="sm:col-span-2">
                  <Button type="button" variant="link" size="sm" onClick={useRecommended}>
                    Use recommended: {workspaceDefaultModel.label}
                  </Button>
                </div>
              )}
            </div>
          )}
        </FormSection>
      )}
    </div>
  );
}
