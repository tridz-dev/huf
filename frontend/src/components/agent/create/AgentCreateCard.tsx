/**
 * AgentCreateCard: the "New agent" one-card flow (OneCardCreate + Fields +
 * TemplateChips + model line). No routing: the parent decides what happens
 * after `onCreate`.
 */
import { useEffect, useRef, useState } from 'react';
import { OneCardCreate, ErrorSummary, focusFirstError, TemplateChips, type FormError } from '@/components/builder';
import { AttentionBanner } from '@/components/patterns';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getWorkspaceDefaultModel } from '@/services/agentForm/agentFormApi';
import { getModels, getProviders } from '@/services/providerApi';

export interface AgentCreateValues {
  agent_name: string;
  instructions: string;
  provider?: string;
  model?: string;
}

export const AGENT_TEMPLATES = [
  { id: 'support', label: 'Customer support', instructions: 'You are a friendly customer support agent. Answer questions clearly using only what you know, ask for missing details, and say so when you are not sure instead of guessing.' },
  { id: 'sales', label: 'Sales', instructions: 'You are a helpful sales assistant. Understand what the customer needs, recommend the right option, answer pricing questions honestly, and suggest a clear next step.' },
  { id: 'helpdesk', label: 'Internal helpdesk', instructions: 'You are an internal helpdesk agent for our team. Answer questions about company processes and tools, point to the right person or document, and keep replies short.' },
  { id: 'research', label: 'Research', instructions: 'You are a research assistant. Break the question down, gather the relevant facts, summarise them clearly, and note anything you could not verify.' },
] as const;

const NON_CHAT = /embed|whisper|tts|speech|moderation|image|dall|rerank|transcri/i;
const isChat = (m: { name: string; model_name?: string; modalities?: string }) => {
  if (NON_CHAT.test(m.model_name || m.name)) return false;
  const mods = (m.modalities || '').toLowerCase();
  return !mods || /text|chat/.test(mods);
};

interface Props {
  onCreate: (values: AgentCreateValues) => void | Promise<void>;
  busy?: boolean;
  onCancel?: () => void;
  /** Shown above the form, e.g. a server error from the last attempt. */
  error?: string;
}

export function AgentCreateCard({ onCreate, busy, onCancel, error }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [name, setName] = useState('');
  const [instructions, setInstructions] = useState('');
  const [template, setTemplate] = useState<string>();
  const [errs, setErrs] = useState<FormError[]>([]);
  const [model, setModel] = useState<{ provider: string | null; model: string | null }>({ provider: null, model: null });
  const [modelState, setModelState] = useState<'loading' | 'ready' | 'none' | 'unavailable'>('loading');
  const [changing, setChanging] = useState(false);
  const [providers, setProviders] = useState<{ name: string; provider_name: string }[]>([]);
  const [models, setModels] = useState<{ name: string; model_name: string }[]>([]);

  useEffect(() => {
    let live = true;
    getWorkspaceDefaultModel()
      .then((d) => { if (!live) return; setModel(d); setModelState(d.model ? 'ready' : 'none'); })
      .catch(() => { if (live) setModelState('unavailable'); });
    return () => { live = false; };
  }, []);

  const startChange = async () => {
    setChanging(true);
    try {
      const ps = (await getProviders()) as { name: string; provider_name: string }[];
      setProviders(ps);
      if (model.provider) setModels(((await getModels(model.provider)) as never[]).filter(isChat));
    } catch { /* selects stay empty */ }
  };
  const pickProvider = async (p: string) => {
    setModel({ provider: p, model: null });
    setModels([]);
    try { setModels(((await getModels(p)) as never[]).filter(isChat)); } catch { /* ignore */ }
  };

  const pick = (id: string) => {
    const t = AGENT_TEMPLATES.find((x) => x.id === id);
    if (!t) return;
    setTemplate(id);
    setInstructions(t.instructions);
    if (!name.trim()) setName(t.label);
  };

  const submit = () => {
    const found: FormError[] = [];
    if (!name.trim()) found.push({ fieldId: 'agent-name', message: 'Give your agent a name' });
    if (!instructions.trim()) found.push({ fieldId: 'agent-instructions', message: 'Add instructions so it knows what to do' });
    setErrs(found);
    if (found.length) { requestAnimationFrame(() => focusFirstError(ref.current)); return; }
    void onCreate({
      agent_name: name.trim(), instructions: instructions.trim(),
      provider: model.provider ?? undefined, model: model.model ?? undefined,
    });
  };
  const errFor = (id: string) => errs.find((e) => e.fieldId === id)?.message;

  return (
    <div ref={ref}>
      <OneCardCreate title="New agent" description="Describe what it should do. You can change everything later."
        submitLabel="Create and try it" onSubmit={submit} busy={busy}
        secondary={onCancel && <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>}>
        <ErrorSummary errors={errs} />
        {error && <p role="alert" className="text-micro text-destructive">{error}</p>}
        <Field label="Name" required id="agent-name" error={errFor('agent-name')}>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Support assistant" autoFocus />
        </Field>
        <TemplateChips items={AGENT_TEMPLATES.map(({ id, label }) => ({ id, label }))} onPick={pick} activeId={template} />
        <Field label="Instructions" required id="agent-instructions" error={errFor('agent-instructions')}
          hint="Tell it who it helps and how to answer.">
          <Textarea rows={6} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
        </Field>
        {modelState === 'none' && (
          <AttentionBanner message="No chat model is set up yet. Add a provider before you try this agent." />
        )}
        {modelState !== 'none' && (
          <div data-testid="model-line" className="flex flex-wrap items-center gap-2 text-ui-text text-steel">
            <span>
              Model:{' '}
              <span className="text-ink">
                {modelState === 'loading' ? 'Checking…' : model.model ?? 'Workspace default'}
              </span>
              {modelState === 'ready' && ' (recommended)'}
            </span>
            {!changing && <Button type="button" variant="link" size="sm" onClick={() => void startChange()}>Change</Button>}
          </div>
        )}
        {changing && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Provider" id="agent-provider">
              <Select value={model.provider ?? ''} onValueChange={(v) => void pickProvider(v)}>
                <SelectTrigger><SelectValue placeholder="Choose a provider" /></SelectTrigger>
                <SelectContent>{providers.map((p) => <SelectItem key={p.name} value={p.name}>{p.provider_name}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Model" id="agent-model">
              <Select value={model.model ?? ''} onValueChange={(v) => setModel((m) => ({ ...m, model: v }))}>
                <SelectTrigger><SelectValue placeholder="Choose a model" /></SelectTrigger>
                <SelectContent>{models.map((m) => <SelectItem key={m.name} value={m.name}>{m.model_name}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          </div>
        )}
      </OneCardCreate>
    </div>
  );
}
