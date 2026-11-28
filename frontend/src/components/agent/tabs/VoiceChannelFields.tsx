/**
 * Voice settings for the Voice calls reveal: the same fields as VoiceTab
 * (voice_engine, voice_config schema fields, voice_greeting, tts_model,
 * tts_voice, stt_model) minus the enable switch. VoiceTab does not export its
 * schema-driven config field, so it is reproduced here.
 */
import { useEffect, useMemo, useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { LinkFieldControl } from '@/components/ui/link-field-control';
import { linkRoutes } from '@/lib/link-routes';
import type { AgentFormValues } from '../types';
import type { AIModel } from '@/types/agent.types';
import {
  MODEL_MODALITY_TTS, MODEL_MODALITY_STT, TTS_MODEL_LABEL, TTS_MODEL_PLACEHOLDER, TTS_MODEL_DESCRIPTION,
  TTS_VOICE_LABEL, TTS_VOICE_PLACEHOLDER, TTS_VOICE_DESCRIPTION, STT_MODEL_LABEL, STT_MODEL_PLACEHOLDER, STT_MODEL_DESCRIPTION,
} from '@/data/ai';
import { listVoiceEngines, getVoiceConfigSchema, type VoiceEngineOption, type VoiceConfigSchemaField } from '@/services/voiceSettingsApi';

const supports = (m: AIModel, req: string) => new Set((m.modalities || '').split(',').map((s) => s.trim()).filter(Boolean)).has(req);

function parseConfig(raw: string | undefined): Record<string, unknown> {
  if (!raw) return {};
  try { const v = JSON.parse(raw); return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; } catch { return {}; }
}
function visible(f: VoiceConfigSchemaField, cfg: Record<string, unknown>): boolean {
  if (!f.visible_when) return true;
  return Object.entries(f.visible_when).every(([k, expected]) => cfg[k] === expected);
}
const hasSecret = (v: unknown) => (typeof v === 'object' && v !== null && 'has_value' in v ? Boolean((v as { has_value: boolean }).has_value) : typeof v === 'string' && v.length > 0);

function ConfigField({ field, value, touched, onChange, onTouch }: { field: VoiceConfigSchemaField; value: unknown; touched: boolean; onChange: (v: unknown) => void; onTouch: () => void }) {
  const id = `voice-config-${field.key}`;
  const help = field.help_text && <p className="text-sm text-steel">{field.help_text}</p>;
  const label = <Label htmlFor={id}>{field.label}</Label>;
  if (field.type === 'boolean') {
    return <div className="flex items-center justify-between rounded-md border p-3"><div>{label}{help}</div><Switch id={id} checked={typeof value === 'boolean' ? value : Boolean(field.default)} onCheckedChange={onChange} /></div>;
  }
  if (field.type === 'select') {
    return (
      <div className="space-y-2">{label}
        <Select value={typeof value === 'string' ? value : (field.default as string) || ''} onValueChange={onChange}>
          <SelectTrigger id={id}><SelectValue placeholder={`Select ${field.label.toLowerCase()}`} /></SelectTrigger>
          <SelectContent>{(field.options || []).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
        </Select>{help}
      </div>
    );
  }
  if (field.type === 'number') {
    const cur = typeof value === 'number' ? value : (field.default as number | undefined);
    return <div className="space-y-2">{label}<Input id={id} type="number" value={cur?.toString() ?? ''} onChange={(e) => onChange(e.target.value === '' ? undefined : Number(e.target.value))} />{help}</div>;
  }
  if (field.type === 'secret') {
    const stored = !touched && hasSecret(value);
    return (
      <div className="space-y-2">{label}
        <Input id={id} type="password" autoComplete="off" placeholder={stored ? 'Value is set — enter a new value to replace it' : 'Not set'}
          value={touched && typeof value === 'string' ? value : ''} onChange={(e) => { onTouch(); onChange(e.target.value); }} />{help}
      </div>
    );
  }
  return <div className="space-y-2">{label}<Input id={id} type="text" value={typeof value === 'string' ? value : (field.default as string) || ''} onChange={(e) => onChange(e.target.value)} />{help}</div>;
}

export function VoiceChannelFields({ form, allModels }: { form: UseFormReturn<AgentFormValues>; allModels: AIModel[] }) {
  const ttsModels = allModels.filter((m) => supports(m, MODEL_MODALITY_TTS));
  const sttModels = allModels.filter((m) => supports(m, MODEL_MODALITY_STT));
  const engine = form.watch('voice_engine');
  const raw = form.watch('voice_config');
  const [engines, setEngines] = useState<VoiceEngineOption[]>([]);
  const [loadingEngines, setLoadingEngines] = useState(true);
  const [schema, setSchema] = useState<VoiceConfigSchemaField[]>([]);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const config = useMemo(() => parseConfig(raw), [raw]);

  useEffect(() => {
    let off = false;
    listVoiceEngines().then((d) => { if (!off) setEngines(d || []); }).catch(() => { if (!off) setEngines([]); }).finally(() => { if (!off) setLoadingEngines(false); });
    return () => { off = true; };
  }, []);
  useEffect(() => {
    if (!engine) { setSchema([]); return; }
    let off = false;
    setLoadingSchema(true);
    getVoiceConfigSchema(engine).then((d) => { if (!off) setSchema(d || []); }).catch(() => { if (!off) setSchema([]); }).finally(() => { if (!off) setLoadingSchema(false); });
    return () => { off = true; };
  }, [engine]);

  const setValue = (k: string, v: unknown) => form.setValue('voice_config', JSON.stringify({ ...config, [k]: v }), { shouldDirty: true });
  const changeEngine = (next: string) => {
    form.setValue('voice_engine', next, { shouldDirty: true });
    if (next !== engine) { form.setValue('voice_config', '{}', { shouldDirty: true }); setTouched({}); }
  };

  return (
    <>
      <FormField control={form.control} name="voice_engine" render={({ field }) => (
        <FormItem>
          <FormLabel>Voice engine</FormLabel>
          <Select onValueChange={changeEngine} value={field.value || ''} disabled={loadingEngines}>
            <FormControl><SelectTrigger><SelectValue placeholder={loadingEngines ? 'Loading voice engines...' : 'Select a voice engine'} /></SelectTrigger></FormControl>
            <SelectContent>
              {engines.length === 0 ? <div className="px-2 py-1.5 text-sm text-steel-soft">No voice engines are installed yet</div>
                : engines.map((e) => <SelectItem key={e.key} value={e.key}>{e.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <FormDescription>Which system runs the voice conversation.</FormDescription>
          <FormMessage />
        </FormItem>
      )} />
      {engine && (
        <div className="space-y-4 rounded-lg border border-line p-4">
          <p className="text-sm font-medium">Engine configuration</p>
          {loadingSchema ? <p className="text-sm text-steel-soft">Loading configuration fields...</p>
            : schema.length === 0 ? <p className="text-sm text-steel-soft">This engine has no additional configuration.</p>
            : schema.filter((f) => visible(f, config)).map((f) => (
              <ConfigField key={f.key} field={f} value={config[f.key]} touched={Boolean(touched[f.key])}
                onChange={(v) => setValue(f.key, v)} onTouch={() => setTouched((t) => ({ ...t, [f.key]: true }))} />
            ))}
        </div>
      )}
      <FormField control={form.control} name="voice_greeting" render={({ field }) => (
        <FormItem>
          <FormLabel>Greeting</FormLabel>
          <FormControl><Textarea placeholder="Hi, how can I help you today?" {...field} value={field.value || ''} /></FormControl>
          <FormDescription>What the agent says first when a call starts.</FormDescription>
          <FormMessage />
        </FormItem>
      )} />
      <FormField control={form.control} name="voice_language" render={({ field }) => (
        <FormItem>
          <FormLabel>Voice language</FormLabel>
          <FormControl><Input placeholder="Auto-detect" {...field} value={field.value || ''} /></FormControl>
          <FormDescription>Leave empty to understand and reply in the language spoken. Set a code or name (e.g. ml, Malayalam) to force it.</FormDescription>
          <FormMessage />
        </FormItem>
      )} />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField control={form.control} name="tts_model" render={({ field }) => (
          <FormItem>
            <FormLabel>{TTS_MODEL_LABEL}</FormLabel>
            <FormControl>
              <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
                <Select onValueChange={(v) => field.onChange(v || undefined)} value={field.value || ''}>
                  <SelectTrigger><SelectValue placeholder={TTS_MODEL_PLACEHOLDER} /></SelectTrigger>
                  <SelectContent>{ttsModels.map((m) => <SelectItem key={m.name} value={m.name}>{m.model_name || m.name}</SelectItem>)}</SelectContent>
                </Select>
              </LinkFieldControl>
            </FormControl>
            <FormDescription>{TTS_MODEL_DESCRIPTION}</FormDescription><FormMessage />
          </FormItem>
        )} />
        <FormField control={form.control} name="tts_voice" render={({ field }) => (
          <FormItem>
            <FormLabel>{TTS_VOICE_LABEL}</FormLabel>
            <FormControl><Input placeholder={TTS_VOICE_PLACEHOLDER} {...field} value={field.value || ''} /></FormControl>
            <FormDescription>{TTS_VOICE_DESCRIPTION}</FormDescription><FormMessage />
          </FormItem>
        )} />
        <FormField control={form.control} name="stt_model" render={({ field }) => (
          <FormItem>
            <FormLabel>{STT_MODEL_LABEL}</FormLabel>
            <FormControl>
              <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
                <Select onValueChange={(v) => field.onChange(v || undefined)} value={field.value || ''}>
                  <SelectTrigger><SelectValue placeholder={STT_MODEL_PLACEHOLDER} /></SelectTrigger>
                  <SelectContent>{sttModels.map((m) => <SelectItem key={m.name} value={m.name}>{m.model_name || m.name}</SelectItem>)}</SelectContent>
                </Select>
              </LinkFieldControl>
            </FormControl>
            <FormDescription>{STT_MODEL_DESCRIPTION}</FormDescription><FormMessage />
          </FormItem>
        )} />
      </div>
    </>
  );
}
