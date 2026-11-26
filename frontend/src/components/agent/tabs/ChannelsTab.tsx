/**
 * ChannelsTab (AF-3, composition state 5): one ToggleReveal per channel.
 * Takes the page's react-hook-form `form` (same as BehaviorTab/VoiceTab/EmbedTab).
 *
 * Field mapping (constraints.md (a)+(b)):
 *  Chat in HUF   allow_chat + persist_conversation kept together (agent.py:178:
 *                on => both true; persist off => chat off). Children:
 *                persist_conversation ("Remember conversations"), persist_user_history,
 *                allow_ask_user, allow_rich_elements, allow_document_artifacts.
 *  Multi-step    enable_multi_run + default_plan; own reveal (multi-run forces allow_chat=false).
 *  Website       embed_enabled (voice embed script); publishable_key, allowed_origins, snippet.
 *  Voice calls   voice_enabled (+ agent_modality: on => Text becomes Both; off =>
 *                Voice becomes Text), children agent_modality preset, then
 *                voice_engine, voice_config (schema fields), voice_greeting,
 *                tts_model, tts_voice, stt_model (VoiceChannelFields).
 *  Automations   no Agent field; renders AutomationsTab. Reveal state is
 *                controlled via automationsOpen/onAutomationsOpenChange or internal.
 */
import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Globe, MessageSquare, Mic, Workflow, ListChecks } from 'lucide-react';
import { toast } from 'sonner';
import { FormSection, PresetSelector, ToggleReveal } from '@/components/builder';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { StatusSentence } from '@/components/patterns';
import type { AIModel, AgentOrchestrationPlanRow } from '@/types/agent.types';
import type { AgentFormValues } from '../types';
import { DefaultPlanTable } from '../DefaultPlanTable';
import { AutomationsTab } from '../AutomationsTab';
import { useDefaultPlanStatus } from '../form/useDefaultPlanStatus';
import { VoiceChannelFields } from './VoiceChannelFields';
import { WidgetSnippet } from './WidgetSnippet';

export interface ChannelsTabProps {
  form: UseFormReturn<AgentFormValues>;
  allModels: AIModel[];
  /** Needed by Run from automations; unsaved agents cannot have automations. */
  agentId?: string;
  /** System agent + non-admin: protected fields read-only. */
  locked?: boolean;
  automationsOpen?: boolean;
  onAutomationsOpenChange?: (open: boolean) => void;
}

function SwitchField({ form, name, label, description, disabled }: {
  form: UseFormReturn<AgentFormValues>;
  name: 'persist_conversation' | 'persist_user_history' | 'allow_ask_user' | 'allow_rich_elements' | 'allow_document_artifacts';
  label: string; description: string; disabled?: boolean;
}) {
  return (
    <FormField control={form.control} name={name} render={({ field }) => (
      <FormItem className="flex flex-row items-center justify-between gap-4 rounded-md border p-3">
        <div className="space-y-0.5"><FormLabel>{label}</FormLabel><FormDescription>{description}</FormDescription></div>
        <FormControl>
          <Switch checked={Boolean(field.value)} disabled={disabled}
            onCheckedChange={(on) => {
              field.onChange(on);
              if (name === 'persist_conversation' && !on) form.setValue('allow_chat', false, { shouldDirty: true });
            }} />
        </FormControl>
      </FormItem>
    )} />
  );
}

export function ChannelsTab({ form, allModels, agentId, locked = false, automationsOpen, onAutomationsOpenChange }: ChannelsTabProps) {
  const allowChat = form.watch('allow_chat');
  const multiRun = form.watch('enable_multi_run');
  const embed = form.watch('embed_enabled') ?? false;
  const voice = form.watch('voice_enabled') ?? false;
  const modality = form.watch('agent_modality');
  const origins = form.watch('allowed_origins');
  const plan = form.watch('default_plan') || [];
  const planStatus = useDefaultPlanStatus(agentId, multiRun === true && plan.length === 0);
  const [autoLocal, setAutoLocal] = useState(Boolean(agentId));
  const autoOpen = automationsOpen ?? autoLocal;
  const setAuto = (v: boolean) => { setAutoLocal(v); onAutomationsOpenChange?.(v); };

  const setChat = (on: boolean) => {
    if (on && multiRun) { toast.warning('Chat is not available for multi-step agents right now.'); return; }
    form.setValue('allow_chat', on, { shouldDirty: true });
    if (on) form.setValue('persist_conversation', true, { shouldDirty: true });
  };
  const setMulti = (on: boolean) => {
    form.setValue('enable_multi_run', on, { shouldDirty: true });
    if (on && form.getValues('allow_chat')) form.setValue('allow_chat', false, { shouldDirty: true });
  };
  const setVoice = (on: boolean) => {
    form.setValue('voice_enabled', on, { shouldDirty: true });
    const m = form.getValues('agent_modality');
    if (on && m === 'Text') form.setValue('agent_modality', 'Both', { shouldDirty: true });
    if (!on && m === 'Voice') form.setValue('agent_modality', 'Text', { shouldDirty: true });
  };
  const planWrite = (rows: AgentOrchestrationPlanRow[]) =>
    form.setValue('default_plan', rows.map((r, i) => ({ ...r, step_index: i + 1 })), { shouldDirty: true });
  const originCount = (origins || '').split('\n').map((s) => s.trim()).filter(Boolean).length;

  return (
    <FormSection title="Channels" description="Where people can reach it. Each switch opens that channel's settings.">
      <ToggleReveal label="Chat in HUF" icon={<MessageSquare className="h-4 w-4" />}
        description="Talk to it in the HUF chat window. History is kept so conversations continue."
        checked={Boolean(allowChat)} disabled={locked || multiRun} onCheckedChange={setChat}>
        {multiRun && <p className="text-micro text-steel">Chat is off while multi-step runs are on.</p>}
        <SwitchField form={form} name="persist_conversation" label="Remember conversations" description="Keeps history within one conversation; it is not shared across chats. Turning it off also turns chat off." />
        <SwitchField form={form} name="persist_user_history" label="Separate history per user" description="Dedicated-conversation automations keep one conversation per person who triggers them. Runs with no person behind them (schedules, webhooks) use the automation's run-as user." />
        <SwitchField form={form} name="allow_ask_user" label="Question buttons" description="Lets it offer buttons and choices instead of plain-text questions. Needs ask_user attached as an action." />
        <SwitchField form={form} name="allow_rich_elements" label="Charts and previews" description="Inline charts, HTML/SVG/mermaid previews and generated media." />
        <SwitchField form={form} name="allow_document_artifacts" label="Long documents" description="Write Markdown/HTML documents, export or redline them when those tools are attached." />
      </ToggleReveal>

      <ToggleReveal label="Multi-step runs" icon={<ListChecks className="h-4 w-4" />}
        description="Plans the steps, runs them in the background and turns chat off." checked={Boolean(multiRun)} onCheckedChange={setMulti}>
        {planStatus.state === 'generating' && <p role="status" className="text-micro text-steel">Generating plan...</p>}
        {planStatus.state === 'failed' && <p role="alert" className="text-micro text-destructive">{`Couldn't generate a plan${planStatus.error ? `: ${planStatus.error}` : ''}. Add the steps yourself or turn multi-step off and on to retry.`}</p>}
        <DefaultPlanTable rows={plan} onAddRow={() => planWrite([...plan, { step_index: plan.length + 1, status: 'pending', instruction: '', output_ref: '' }])}
          onRemoveRow={(i) => planWrite(plan.filter((_, j) => j !== i))}
          onUpdateRow={(i, f, v) => planWrite(plan.map((r, j) => (j === i ? { ...r, [f]: v } : r)))} />
      </ToggleReveal>

      <ToggleReveal label="Website widget" icon={<Globe className="h-4 w-4" />}
        description="Lets visitors start a voice session from your site using a publishable key." checked={embed}
        onCheckedChange={(on) => form.setValue('embed_enabled', on, { shouldDirty: true })}
        status={<StatusSentence tone={originCount ? 'ready' : 'attention'}>{originCount ? `Live on ${originCount} ${originCount === 1 ? 'domain' : 'domains'}` : 'Add a domain'}</StatusSentence>}>
        <FormField control={form.control} name="publishable_key" render={({ field }) => (
          <FormItem>
            <FormLabel>Publishable key</FormLabel>
            <FormControl><Input {...field} value={field.value ?? ''} readOnly placeholder="Created when you save" /></FormControl>
            <FormDescription>Auto-generated and safe to put in your site code. Scoped to this agent.</FormDescription><FormMessage />
          </FormItem>
        )} />
        <FormField control={form.control} name="allowed_origins" render={({ field }) => (
          <FormItem>
            <FormLabel>Allowed domains</FormLabel>
            <FormControl><Textarea {...field} value={field.value ?? ''} placeholder="https://example.com" rows={3} /></FormControl>
            <FormDescription>One per line. Requests from other sites are rejected.</FormDescription><FormMessage />
          </FormItem>
        )} />
        <WidgetSnippet publishableKey={form.watch('publishable_key')} agentId={agentId} />
      </ToggleReveal>

      <ToggleReveal label="Voice calls" icon={<Mic className="h-4 w-4" />}
        description="Let people talk to it. Same instructions, actions and knowledge as text."
        checked={Boolean(voice)} disabled={locked} onCheckedChange={setVoice}>
        <div className="space-y-1.5">
          <Label>Mode</Label>
          <PresetSelector label="Modality" value={modality === 'Voice' ? 'Voice' : 'Both'}
            presets={[{ value: 'Both', label: 'Text and voice', description: 'Chat and calls', recommended: true }, { value: 'Voice', label: 'Voice only', description: 'Hides text-only setup' }]}
            onChange={(v) => form.setValue('agent_modality', v as 'Voice' | 'Both', { shouldDirty: true })} />
        </div>
        <VoiceChannelFields form={form} allModels={allModels} />
      </ToggleReveal>

      <ToggleReveal label="Run from automations" icon={<Workflow className="h-4 w-4" />}
        description="Run it on a schedule, a document change or an outside event." checked={autoOpen} onCheckedChange={setAuto}>
        {agentId ? <AutomationsTab agentId={agentId} /> : <p className="text-ui-text text-steel">Save the agent first, then add automations.</p>}
      </ToggleReveal>
    </FormSection>
  );
}
