/**
 * AgentCreateCard: the "New agent" one-card flow (OneCardCreate + Fields +
 * TemplateChips + model line). No routing: the parent decides what happens
 * after `onCreate`.
 */
import { useEffect, useRef, useState } from 'react';
import { OneCardCreate, ErrorSummary, focusFirstError, TemplateChips, TemplateGallery, type FormError } from '@/components/builder';
import { AttentionBanner } from '@/components/patterns';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AGENT_EXAMPLES, type AgentExample } from './agentExamples';
import { getWorkspaceDefaultModel } from '@/services/agentForm/agentFormApi';
import { getModels, getProviders } from '@/services/providerApi';

export interface AgentCreateValues {
  agent_name: string;
  instructions: string;
  provider?: string;
  model?: string;
}

/** Featured examples shown as chips; the full set lives in the gallery. */
export const AGENT_TEMPLATES = AGENT_EXAMPLES.filter((e) => e.featured);
const toChip = (e: AgentExample) => ({ id: e.id, label: e.label, description: e.description, meta: e.sets, category: e.category });

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
  const [gallery, setGallery] = useState(false);
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
    const t = AGENT_EXAMPLES.find((x) => x.id === id);
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
          <Input id="agent-name" aria-invalid={errFor('agent-name') ? true : undefined} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Support assistant" autoFocus />
        </Field>
        <Field label="Instructions" required id="agent-instructions" error={errFor('agent-instructions')}
          hint="Say who it helps, what it can look up or change, and when to hand off to a person.">
          <Textarea id="agent-instructions" aria-describedby="agent-instructions-note" aria-invalid={errFor('agent-instructions') ? true : undefined} rows={6} value={instructions} onChange={(e) => setInstructions(e.target.value)}
            placeholder="Describe what this agent should do — e.g. answer order questions from our Orders table and escalate refunds over $200 to a person." />
        </Field>
        <TemplateChips lead="Or start from an example:" label="Example agents" items={AGENT_TEMPLATES.map(toChip)}
          onPick={pick} activeId={template} onMore={() => setGallery(true)} />
        <TemplateGallery open={gallery} onOpenChange={setGallery} items={AGENT_EXAMPLES.map(toChip)} onPick={pick}
          activeId={template} title="Example agents" description="Each one fills in a name and instructions. Edit them, then connect knowledge, tables and channels after you create it." />
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
