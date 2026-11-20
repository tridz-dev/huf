/**
 * AdvancedPresetsTab: Creativity + Thinking presets, limits, Developer options, danger zone slot.
 * Controlled by the page's react-hook-form (AgentFormValues).
 *
 * Field mapping (constraints.md (a)+(b), Advanced tab + General tab LLM/caching fields):
 *   Main path
 *     temperature ................ Creativity PresetSelector (precise 0.2 / balanced 0.7 / creative 1.0 / Custom slider 0-2)
 *     reasoning_mode, reasoning_effort ... Thinking PresetSelector (off / auto / light / deep / Custom selects)
 *     reasoning_budget_tokens .... Thinking Custom (mode On or Auto), reasoning_summary ... Thinking Custom
 *     context_strategy, history_limit, max_turns, max_knowledge_tokens, max_context_chars ... Limits
 *   Developer options (SettingsAdvanced, collapsed)
 *     top_p, run_immediately
 *     prompt_cache_mode, enable_prompt_caching (Advanced mode), cache_control_type, cache_system_message,
 *       cache_conversation_history (+ unsupported-model warning via `cacheStatus`)
 *     summary_ratio, summary_model, summary_prompt_mode, summary_prompt_template, summary_prompt,
 *       summary_prompt_version_locked, summary_template_version_at_attach (only when context_strategy = Summarize)
 *     enable_conversation_data, inject_conversation_data
 *     enable_memory, memory_policy, enable_memory_search_tool, enable_memory_write_tool
 *     agent_color, show_tool_execution_details, autonaming_of_conversation_title
 *     image_generation_model (Image modality models)
 *     allow_file_upload, enable_ocr, max_upload_size_mb
 *   Danger zone: `dangerZone` ReactNode (page wires DangerZone + ConfirmDestructive delete flow).
 * Voice-only hides text-model blocks (creativity, limits, summary, caching, top_p, image, upload, autonaming), as AdvancedTab did.
 * conversation_data_api_permission lives in AccessTab (needs enable_conversation_data, set here).
 */
import { useState, type ReactNode } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { LinkFieldControl } from '@/components/ui/link-field-control';
import { linkRoutes } from '@/lib/link-routes';
import { CUSTOM_PRESET, FormSection, PresetSelector, ToggleRow } from '@/components/builder';
import { AttentionBanner, SettingsAdvanced } from '@/components/patterns';
import { MODEL_MODALITY_IMAGE, IMAGE_MODEL_LABEL, IMAGE_MODEL_PLACEHOLDER, IMAGE_MODEL_DESCRIPTION } from '@/data/ai';
import type { AIModel } from '@/types/agent.types';
import type { AgentPromptOption } from '../PromptTemplateSection';
import type { MemoryPolicyOption } from '../AdvancedTab';
import {
  CREATIVITY_PRESETS, presetToReasoning, presetToTemperature, reasoningToPreset, temperatureToPreset,
  type CreativityPreset, type ThinkingPreset,
} from './presets';
import { BoolRow, NumberField, SelectField, useFormBinding, type AgentForm } from './fields';

export interface AdvancedPresetsTabProps {
  form: AgentForm;
  allModels: AIModel[];
  summaryPromptOptions: AgentPromptOption[];
  loadingSummaryPrompts?: boolean;
  memoryPolicyOptions?: MemoryPolicyOption[];
  loadingMemoryPolicies?: boolean;
  /** Result of checkCacheableModels for the chosen model; renders the "not supported" notice. */
  cacheStatus?: { supported: boolean; alternatives: string[] } | null;
  /** Page navigates to the "new summary prompt" screen. */
  onCreateSummaryPrompt?: () => void;
  /** Rendered last, e.g. <DangerZone/> that opens ConfirmDestructive. Omitted for new agents. */
  dangerZone?: ReactNode;
  locked?: boolean;
}

const CREATIVITY = [
  { value: 'precise', label: 'Precise', description: 'Same answer every time' },
  { value: 'balanced', label: 'Balanced', description: 'Good for most', recommended: true },
  { value: 'creative', label: 'Creative', description: 'More varied wording' },
] as const;

const THINKING = [
  { value: 'off', label: 'Off', description: 'Answers straight away' },
  { value: 'auto', label: 'Automatic', description: 'The model decides', recommended: true },
  { value: 'light', label: 'Light', description: 'A little extra thought' },
  { value: 'deep', label: 'Deep', description: 'Slower, for hard tasks' },
] as const;

const bool = (v: boolean | undefined) => Boolean(v);

export function AdvancedPresetsTab({
  form, allModels, summaryPromptOptions, loadingSummaryPrompts = false, memoryPolicyOptions = [],
  loadingMemoryPolicies = false, cacheStatus, onCreateSummaryPrompt, dangerZone, locked = false,
}: AdvancedPresetsTabProps) {
  const { get, set, error } = useFormBinding(form);
  const isVoiceOnly = get('agent_modality') === 'Voice';

  const temperature = get('temperature');
  const creativity = temperatureToPreset(temperature);
  // Picking Custom must stay on Custom even while the slider still sits on a preset value.
  const [forceCustomCreativity, setForceCustomCreativity] = useState(false);
  const creativityValue = forceCustomCreativity ? CUSTOM_PRESET : creativity === 'custom' ? CUSTOM_PRESET : creativity;

  const mode = get('reasoning_mode') ?? 'Auto';
  const effort = get('reasoning_effort') ?? 'Auto';
  const thinking = reasoningToPreset(mode, effort);
  const [forceCustomThinking, setForceCustomThinking] = useState(false);
  const thinkingValue = forceCustomThinking ? CUSTOM_PRESET : thinking === 'custom' ? CUSTOM_PRESET : thinking;

  const strategy = get('context_strategy');
  const summaryMode = get('summary_prompt_mode') ?? 'Local';
  const enableConversationData = bool(get('enable_conversation_data'));
  const enableMemory = bool(get('enable_memory'));
  const cacheMode = get('prompt_cache_mode') ?? 'Auto';
  const cachingOn = bool(get('enable_prompt_caching'));
  const imageModels = allModels.filter((m) => (m.modalities || '').split(',').map((s) => s.trim()).includes(MODEL_MODALITY_IMAGE));
  const selectedSummaryPrompt = summaryPromptOptions.find((o) => o.value === get('summary_prompt_template'));

  return (
    <div className="space-y-6">
      {!isVoiceOnly && (
        <FormSection title="Creativity" description="How much the wording varies from one answer to the next.">
          <PresetSelector label="Creativity" value={creativityValue}
            onChange={(v) => {
              if (locked) return;
              if (v === CUSTOM_PRESET) { setForceCustomCreativity(true); return; }
              setForceCustomCreativity(false);
              set('temperature', presetToTemperature(v as CreativityPreset));
            }}
            presets={[...CREATIVITY]}
            custom={
              <Field label={`Temperature: ${temperature ?? CREATIVITY_PRESETS.balanced}`} hint="0 is focused and repeatable, 2 is very varied." error={error('temperature')}>
                {(p) => <Slider id={p.id} min={0} max={2} step={0.1} value={[temperature ?? CREATIVITY_PRESETS.balanced]} onValueChange={(vals) => set('temperature', vals[0])} />}
              </Field>
            } />
        </FormSection>
      )}

      <FormSection title="Thinking" description="Let the model reason before it answers. Helps on multi-step problems, costs time and tokens.">
        <PresetSelector label="Thinking" value={thinkingValue}
          onChange={(v) => {
            if (locked) return;
            if (v === CUSTOM_PRESET) { setForceCustomThinking(true); return; }
            setForceCustomThinking(false);
            const r = presetToReasoning(v as ThinkingPreset);
            set('reasoning_mode', r.reasoning_mode);
            set('reasoning_effort', r.reasoning_effort);
          }}
          presets={[...THINKING]}
          custom={
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <SelectField label="Reasoning mode" value={mode} onChange={(v) => set('reasoning_mode', v as 'Auto' | 'Off' | 'On')}
                  options={[{ value: 'Auto', label: 'Auto (model native)' }, { value: 'Off', label: 'Off (force disable)' }, { value: 'On', label: 'On (force enable)' }]} />
                <SelectField label="Reasoning effort" value={effort} onChange={(v) => set('reasoning_effort', v as 'Auto' | 'Low' | 'Medium' | 'High')}
                  options={[{ value: 'Auto', label: 'Auto' }, { value: 'Low', label: 'Low' }, { value: 'Medium', label: 'Medium' }, { value: 'High', label: 'High' }]} />
              </div>
              {['On', 'Auto'].includes(mode) && (
                <NumberField label="Reasoning budget tokens" placeholder="1024" value={get('reasoning_budget_tokens')} onChange={(v) => set('reasoning_budget_tokens', v)}
                  hint="Explicit token budget for thinking (mainly Anthropic thinking models)." error={error('reasoning_budget_tokens')} />
              )}
              <SelectField label="Reasoning summary" value={get('reasoning_summary') || 'None'} onChange={(v) => set('reasoning_summary', v as 'None' | 'Concise' | 'Detailed')}
                hint="Ask for a reasoning summary (OpenAI Responses API)."
                options={[{ value: 'None', label: 'None' }, { value: 'Concise', label: 'Concise' }, { value: 'Detailed', label: 'Detailed' }]} />
            </>
          } />
      </FormSection>

      {!isVoiceOnly && (
        <FormSection title="Limits" description="Caps on how long a run and a conversation can get.">
          <SelectField label="When a conversation gets long" value={strategy} onChange={(v) => set('context_strategy', v)}
            hint="Summarize compresses old messages with a model; FIFO drops the oldest; None keeps everything." placeholder="Choose a strategy"
            options={[{ value: 'Summarize', label: 'Summarize' }, { value: 'FIFO', label: 'FIFO' }, { value: 'None', label: 'None' }]} />
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField label="History limit" placeholder="50" value={get('history_limit')} onChange={(v) => set('history_limit', v)} hint="Messages kept in context." />
            <NumberField label="Max turns" placeholder="10" value={get('max_turns')} onChange={(v) => set('max_turns', v)} hint="Consecutive actions in one run." />
            <NumberField label="Max knowledge tokens" placeholder="2000" value={get('max_knowledge_tokens')} onChange={(v) => set('max_knowledge_tokens', v)} hint="Budget for injected knowledge." />
            <NumberField label="Max context characters" placeholder="2000" value={get('max_context_chars')} onChange={(v) => set('max_context_chars', v)} hint="Tool results are truncated beyond this." />
          </div>
        </FormSection>
      )}

      <FormSection title="Developer options" description="Raw model settings. The defaults work for most agents.">
        <SettingsAdvanced label="Show developer options">
          {!isVoiceOnly && (
            <>
              <Field label={`Top P: ${get('top_p') ?? 1}`} hint="Alternative to creativity. Change this or creativity, not both." error={error('top_p')}>
                {(p) => <Slider id={p.id} min={0} max={1} step={0.05} value={[get('top_p') ?? 1]} onValueChange={(vals) => set('top_p', vals[0])} />}
              </Field>
              <div className="rounded-lg border border-line">
                <BoolRow form={form} name="run_immediately" title="Run immediately"
                  description="Replies synchronously instead of queueing. Use only for trusted calls that need an instant response." />
                <BoolRow form={form} name="autonaming_of_conversation_title" title="Name conversations automatically" description="Generate a title for each new conversation." />
              </div>

              <SelectField label="Prompt caching" value={cacheMode} onChange={(v) => set('prompt_cache_mode', v as 'Auto' | 'Off' | 'Advanced')} disabled={locked}
                hint="Auto lets HUF choose; Off disables HUF-injected caching; Advanced shows the controls below."
                options={[{ value: 'Auto', label: 'Auto' }, { value: 'Off', label: 'Off' }, { value: 'Advanced', label: 'Advanced' }]} />
              {cacheMode === 'Advanced' && (
                <div className="rounded-lg border border-line">
                  <BoolRow form={form} name="enable_prompt_caching" title="Enable prompt caching" description="Cache repeated prompt content to cut token cost. Supported providers only." />
                </div>
              )}
              {cacheMode === 'Advanced' && cachingOn && cacheStatus && !cacheStatus.supported && (
                <AttentionBanner message={`This model does not support prompt caching, so it will be skipped.${cacheStatus.alternatives.length ? ` Supported: ${cacheStatus.alternatives.slice(0, 5).join(', ')}.` : ''}`} />
              )}
              {cacheMode === 'Advanced' && cachingOn && (
                <>
                  <SelectField label="Cache control type" value={get('cache_control_type')} onChange={(v) => set('cache_control_type', v)}
                    hint="ephemeral for Anthropic (charges for cache writes); auto for OpenAI / Deepseek." placeholder="Choose a type"
                    options={[{ value: 'auto', label: 'Auto' }, { value: 'ephemeral', label: 'Ephemeral' }]} />
                  <div className="rounded-lg border border-line">
                    <BoolRow form={form} name="cache_system_message" title="Cache system message" description="Do not re-send the instructions on every request." />
                    <BoolRow form={form} name="cache_conversation_history" title="Cache conversation history" description="Cut token use in multi-turn chats." />
                  </div>
                </>
              )}

              {strategy === 'Summarize' && (
                <div className="space-y-4 rounded-lg border border-line p-4">
                  <p className="text-ui-text font-medium text-ink">Summaries</p>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <NumberField label="Summary ratio" float step={0.05} placeholder="0.7" value={get('summary_ratio')} onChange={(v) => set('summary_ratio', v)} hint="Fraction of history to compress (0.7 = 70%)." />
                    <Field label="Summary model" hint="Dedicated lightweight model.">
                      {(p) => (
                        <LinkFieldControl value={get('summary_model')} linkTo={linkRoutes.aiModel}>
                          <Combobox id={p.id} options={allModels.map((m) => ({ value: m.name, label: m.model_name || m.name }))} value={get('summary_model') ?? ''}
                            onValueChange={(v) => set('summary_model', v || undefined)} placeholder="Default (main agent model)" searchPlaceholder="Search models..." emptyText="No models found" />
                        </LinkFieldControl>
                      )}
                    </Field>
                  </div>
                  <div className="rounded-lg border border-line">
                    <ToggleRow title="Use external template" description="Link a reusable summary prompt instead of writing one here."
                      checked={summaryMode === 'Template'} onCheckedChange={(on) => set('summary_prompt_mode', on ? 'Template' : 'Local')} />
                  </div>
                </div>
              )}
            </>
          )}
          {!isVoiceOnly && strategy === 'Summarize' && (
            <div className="space-y-4 rounded-lg border border-line p-4">
              {summaryMode === 'Template' ? (
                <>
                  <Field label="Summary prompt template" required error={error('summary_prompt_template')} id="summary_prompt_template">
                    {(p) => (
                      <div className="flex items-center gap-2">
                        <Combobox id={p.id} options={summaryPromptOptions.map((o) => ({ ...o, subtitle: o.version ? `Version ${o.version}` : undefined }))}
                          value={get('summary_prompt_template') ?? ''} onValueChange={(v) => set('summary_prompt_template', v)} disabled={loadingSummaryPrompts}
                          placeholder={loadingSummaryPrompts ? 'Loading templates...' : 'Select a summary prompt'} searchPlaceholder="Search summary templates..."
                          emptyText="No active summary prompt templates found." linkTo={linkRoutes.agentSummaryPrompt} />
                        {onCreateSummaryPrompt && (
                          <Button type="button" variant="secondary" onClick={onCreateSummaryPrompt}><Plus className="mr-2 h-4 w-4" />New</Button>
                        )}
                      </div>
                    )}
                  </Field>
                  {selectedSummaryPrompt?.version != null && (
                    <p className="text-micro text-steel">Version {selectedSummaryPrompt.version}{selectedSummaryPrompt.isLatest ? ' (latest)' : ''}</p>
                  )}
                  <div className="rounded-lg border border-line">
                    <BoolRow form={form} name="summary_prompt_version_locked" title="Lock summary prompt version" description="Stay on the attached version when the template changes." />
                  </div>
                  <Field label="Attached at version">
                    <Input readOnly value={get('summary_template_version_at_attach')?.toString() ?? ''} />
                  </Field>
                </>
              ) : (
                <Field label="Summary prompt" hint="Used to summarize conversation history.">
                  <Textarea className="min-h-[96px] resize-y" placeholder="Summarize the conversation so far..." value={get('summary_prompt') ?? ''} onChange={(e) => set('summary_prompt', e.target.value)} />
                </Field>
              )}
            </div>
          )}

          <div className="rounded-lg border border-line">
            <BoolRow form={form} name="enable_conversation_data" title="Allow conversation data management" description="Let the agent store and read data across a conversation. Access level is set under Access." />
            {enableConversationData && <BoolRow form={form} name="inject_conversation_data" title="Inject conversation data into prompt" description="Include stored conversation data in every prompt." />}
            <BoolRow form={form} name="enable_memory" title="Enable memory" description="Long-term, scoped memory for this agent." />
            {enableMemory && (
              <>
                <BoolRow form={form} name="enable_memory_search_tool" title="Enable memory search tool" />
                <BoolRow form={form} name="enable_memory_write_tool" title="Enable memory write tool" />
              </>
            )}
            <BoolRow form={form} name="show_tool_execution_details" title="Show tool execution details" description="Show each tool call and its result in the chat." />
          </div>
          {enableMemory && (
            <Field label="Memory policy" hint="Which memories may be stored and recalled.">
              {(p) => (
                <Combobox id={p.id} options={memoryPolicyOptions.map((o) => ({ value: o.value, label: o.label }))} value={get('memory_policy') ?? ''}
                  onValueChange={(v) => set('memory_policy', v || undefined)} disabled={loadingMemoryPolicies}
                  placeholder={loadingMemoryPolicies ? 'Loading policies...' : 'Select a memory policy'} searchPlaceholder="Search memory policies..." emptyText="No memory policies found." linkTo={linkRoutes.memoryPolicy} />
              )}
            </Field>
          )}

          <Field label="Agent color" hint="Six-digit hex color starting with #." error={error('agent_color')}>
            {(p) => (
            <div className="flex items-center gap-2">
              <Input {...p} placeholder="#______" value={get('agent_color') ?? ''} onChange={(e) => set('agent_color', e.target.value)} />
            </div>
            )}
          </Field>

          {!isVoiceOnly && (
            <>
              <Field label={IMAGE_MODEL_LABEL} hint={IMAGE_MODEL_DESCRIPTION}>
                {(p) => (
                  <LinkFieldControl value={get('image_generation_model')} linkTo={linkRoutes.aiModel}>
                    <Combobox id={p.id} options={imageModels.map((m) => ({ value: m.name, label: m.model_name || m.name }))} value={get('image_generation_model') ?? ''}
                      onValueChange={(v) => set('image_generation_model', v || undefined)} placeholder={IMAGE_MODEL_PLACEHOLDER} searchPlaceholder="Search image models..." emptyText="No image models found" />
                  </LinkFieldControl>
                )}
              </Field>
              <div className="rounded-lg border border-line">
                <BoolRow form={form} name="allow_file_upload" title="Allow file upload" description="Let people attach documents in chat." />
                {bool(get('allow_file_upload')) && <BoolRow form={form} name="enable_ocr" title="Enable OCR" description="Read text from images and scans. The model must support OCR." />}
              </div>
              {bool(get('allow_file_upload')) && (
                <NumberField label="Max upload size (MB)" placeholder="25" value={get('max_upload_size_mb')} onChange={(v) => set('max_upload_size_mb', v)} error={error('max_upload_size_mb')} />
              )}
            </>
          )}
        </SettingsAdvanced>
      </FormSection>

      {dangerZone}
    </div>
  );
}
