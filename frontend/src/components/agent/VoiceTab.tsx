import { useEffect, useMemo, useState } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { LinkFieldControl } from '@/components/ui/link-field-control';
import { linkRoutes } from '@/lib/link-routes';
import { FormSettingsSection } from './FormSettingsSection';
import type { AgentFormValues } from './types';
import type { AIModel } from '@/types/agent.types';
import {
  MODEL_MODALITY_TTS,
  MODEL_MODALITY_STT,
  TTS_MODEL_LABEL,
  TTS_MODEL_PLACEHOLDER,
  TTS_MODEL_DESCRIPTION,
  TTS_VOICE_LABEL,
  TTS_VOICE_PLACEHOLDER,
  TTS_VOICE_DESCRIPTION,
  STT_MODEL_LABEL,
  STT_MODEL_PLACEHOLDER,
  STT_MODEL_DESCRIPTION,
} from '@/data/ai';
import {
  listVoiceEngines,
  getVoiceConfigSchema,
  type VoiceEngineOption,
  type VoiceConfigSchemaField,
} from '@/services/voiceSettingsApi';

interface VoiceTabProps {
  form: UseFormReturn<AgentFormValues>;
  allModels: AIModel[];
}

function modelSupports(model: AIModel, required: string): boolean {
  const items = new Set(
    (model.modalities || '')
      .split(',')
      .map((m) => m.trim())
      .filter(Boolean),
  );
  return items.has(required);
}

/** True when a stored config entry represents a redacted secret rather than a usable value. */
function looksLikeRedactedSecret(value: unknown): value is { has_value: boolean } {
  return typeof value === 'object' && value !== null && 'has_value' in (value as Record<string, unknown>);
}

/** True when a stored config entry indicates a secret has already been set server-side. */
function secretHasStoredValue(value: unknown): boolean {
  if (looksLikeRedactedSecret(value)) {
    return Boolean((value as { has_value: boolean }).has_value);
  }
  // Belt-and-suspenders: some engines may not yet redact on the way back, but a
  // secret value must never be rendered into the DOM regardless of its shape.
  return typeof value === 'string' && value.length > 0;
}

function parseVoiceConfig(raw: string | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function fieldVisible(field: VoiceConfigSchemaField, config: Record<string, unknown>): boolean {
  if (!field.visible_when) return true;
  return Object.entries(field.visible_when).every(([key, expected]) => config[key] === expected);
}

export function VoiceTab({ form, allModels }: VoiceTabProps) {
  const ttsModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_TTS));
  const sttModels = allModels.filter((m) => modelSupports(m, MODEL_MODALITY_STT));

  const voiceEnabled = form.watch('voice_enabled');
  const voiceEngine = form.watch('voice_engine');
  const voiceConfigRaw = form.watch('voice_config');

  const [engines, setEngines] = useState<VoiceEngineOption[]>([]);
  const [loadingEngines, setLoadingEngines] = useState(false);
  const [schema, setSchema] = useState<VoiceConfigSchemaField[]>([]);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [schemaEngine, setSchemaEngine] = useState<string | undefined>(undefined);
  // Fields the user has explicitly retyped in this session — only these
  // overwrite a previously stored secret value on save.
  const [touchedSecrets, setTouchedSecrets] = useState<Record<string, boolean>>({});

  const config = useMemo(() => parseVoiceConfig(voiceConfigRaw), [voiceConfigRaw]);

  useEffect(() => {
    if (!voiceEnabled) return;
    if (engines.length > 0 || loadingEngines) return;
    setLoadingEngines(true);
    listVoiceEngines()
      .then((data) => setEngines(data || []))
      .catch(() => setEngines([]))
      .finally(() => setLoadingEngines(false));
  }, [voiceEnabled, engines.length, loadingEngines]);

  useEffect(() => {
    if (!voiceEngine) {
      setSchema([]);
      setSchemaEngine(undefined);
      return;
    }
    if (schemaEngine === voiceEngine) return;

    let cancelled = false;
    setLoadingSchema(true);
    getVoiceConfigSchema(voiceEngine)
      .then((data) => {
        if (cancelled) return;
        setSchema(data || []);
        setSchemaEngine(voiceEngine);
      })
      .catch(() => {
        if (!cancelled) {
          setSchema([]);
          setSchemaEngine(voiceEngine);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingSchema(false);
      });

    return () => {
      cancelled = true;
    };
  }, [voiceEngine, schemaEngine]);

  const updateConfigValue = (key: string, value: unknown) => {
    const next = { ...config, [key]: value };
    form.setValue('voice_config', JSON.stringify(next), { shouldDirty: true });
  };

  const handleEngineChange = (nextEngine: string) => {
    form.setValue('voice_engine', nextEngine, { shouldDirty: true });
    if (nextEngine !== voiceEngine) {
      // Switching engines invalidates the previous engine's config shape.
      form.setValue('voice_config', '{}', { shouldDirty: true });
      setTouchedSecrets({});
    }
  };

  return (
    <div className="space-y-12">
      <FormSettingsSection
        title="Voice"
        description="Let users talk to this agent instead of just typing. The same instructions, tools, and knowledge apply on voice as on text."
      >
        <FormField
          control={form.control}
          name="voice_enabled"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
              <div className="space-y-0.5 pr-4">
                <FormLabel className="text-base">Enable Voice</FormLabel>
                <FormDescription>
                  Let users talk to this agent, not just type. Voice and text are two ways into the same
                  agent.
                </FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        {voiceEnabled && (
          <>
            <FormField
              control={form.control}
              name="voice_engine"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Voice Engine</FormLabel>
                  <Select onValueChange={handleEngineChange} value={field.value || ''} disabled={loadingEngines}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue
                          placeholder={loadingEngines ? 'Loading voice engines...' : 'Select a voice engine'}
                        />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {engines.length === 0 ? (
                        <div className="px-2 py-1.5 text-sm text-steel-soft">
                          No voice engines are installed yet
                        </div>
                      ) : (
                        engines.map((engine) => (
                          <SelectItem key={engine.key} value={engine.key}>
                            {engine.label}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <FormDescription>Which system runs the voice conversation.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {voiceEngine && (
              <div className="space-y-6 rounded-none border p-4">
                <p className="text-sm font-medium">Engine Configuration</p>
                {loadingSchema ? (
                  <p className="text-sm text-steel-soft">Loading configuration fields...</p>
                ) : schema.length === 0 ? (
                  <p className="text-sm text-steel-soft">This engine has no additional configuration.</p>
                ) : (
                  schema
                    .filter((schemaField) => fieldVisible(schemaField, config))
                    .map((schemaField) => (
                      <VoiceConfigField
                        key={schemaField.key}
                        field={schemaField}
                        value={config[schemaField.key]}
                        touched={Boolean(touchedSecrets[schemaField.key])}
                        onChange={(value) => updateConfigValue(schemaField.key, value)}
                        onTouch={() =>
                          setTouchedSecrets((prev) => ({ ...prev, [schemaField.key]: true }))
                        }
                      />
                    ))
                )}
              </div>
            )}

            <FormField
              control={form.control}
              name="voice_greeting"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Greeting</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Hi, how can I help you today?"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormDescription>What the agent says first when a call starts.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </>
        )}
      </FormSettingsSection>

      <FormSettingsSection
        title="Audio Models"
        description="Optional: select dedicated models for audio generation (TTS) and transcription (STT)."
      >
        <div className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="tts_model"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{TTS_MODEL_LABEL}</FormLabel>
                <FormControl>
                  <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
                    <Select onValueChange={(v) => field.onChange(v || undefined)} value={field.value || ''}>
                      <SelectTrigger>
                        <SelectValue placeholder={TTS_MODEL_PLACEHOLDER} />
                      </SelectTrigger>
                      <SelectContent>
                        {ttsModels.map((m) => (
                          <SelectItem key={m.name} value={m.name}>
                            {m.model_name || m.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </LinkFieldControl>
                </FormControl>
                <FormDescription>{TTS_MODEL_DESCRIPTION}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="tts_voice"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{TTS_VOICE_LABEL}</FormLabel>
                <FormControl>
                  <Input placeholder={TTS_VOICE_PLACEHOLDER} {...field} value={field.value || ''} />
                </FormControl>
                <FormDescription>{TTS_VOICE_DESCRIPTION}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="stt_model"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{STT_MODEL_LABEL}</FormLabel>
                <FormControl>
                  <LinkFieldControl value={field.value} linkTo={linkRoutes.aiModel}>
                    <Select onValueChange={(v) => field.onChange(v || undefined)} value={field.value || ''}>
                      <SelectTrigger>
                        <SelectValue placeholder={STT_MODEL_PLACEHOLDER} />
                      </SelectTrigger>
                      <SelectContent>
                        {sttModels.map((m) => (
                          <SelectItem key={m.name} value={m.name}>
                            {m.model_name || m.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </LinkFieldControl>
                </FormControl>
                <FormDescription>{STT_MODEL_DESCRIPTION}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </FormSettingsSection>
    </div>
  );
}

interface VoiceConfigFieldProps {
  field: VoiceConfigSchemaField;
  value: unknown;
  touched: boolean;
  onChange: (value: unknown) => void;
  onTouch: () => void;
}

/** One schema-driven input, switched on the engine-declared field `type`. */
function VoiceConfigField({ field, value, touched, onChange, onTouch }: VoiceConfigFieldProps) {
  const fieldId = `voice-config-${field.key}`;

  if (field.type === 'boolean') {
    const checked = typeof value === 'boolean' ? value : Boolean(field.default);
    return (
      <div className="flex flex-row items-center justify-between rounded-none border p-4">
        <div className="space-y-0.5 pr-4">
          <label htmlFor={fieldId} className="text-base font-medium">
            {field.label}
          </label>
          {field.help_text && <p className="text-sm text-steel">{field.help_text}</p>}
        </div>
        <Switch id={fieldId} checked={checked} onCheckedChange={(v) => onChange(v)} />
      </div>
    );
  }

  if (field.type === 'select') {
    const currentValue = typeof value === 'string' ? value : (field.default as string | undefined) || '';
    return (
      <div className="space-y-2">
        <label htmlFor={fieldId} className="text-sm font-medium">
          {field.label}
        </label>
        <Select value={currentValue} onValueChange={(v) => onChange(v)}>
          <SelectTrigger id={fieldId}>
            <SelectValue placeholder={`Select ${field.label.toLowerCase()}`} />
          </SelectTrigger>
          <SelectContent>
            {(field.options || []).map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {field.help_text && <p className="text-sm text-steel">{field.help_text}</p>}
      </div>
    );
  }

  if (field.type === 'number') {
    const currentValue = typeof value === 'number' ? value : (field.default as number | undefined);
    return (
      <div className="space-y-2">
        <label htmlFor={fieldId} className="text-sm font-medium">
          {field.label}
        </label>
        <Input
          id={fieldId}
          type="number"
          value={currentValue?.toString() ?? ''}
          onChange={(e) => {
            const raw = e.target.value;
            onChange(raw === '' ? undefined : Number(raw));
          }}
        />
        {field.help_text && <p className="text-sm text-steel">{field.help_text}</p>}
      </div>
    );
  }

  if (field.type === 'secret') {
    const hasStoredValue = !touched && secretHasStoredValue(value);
    return (
      <div className="space-y-2">
        <label htmlFor={fieldId} className="text-sm font-medium">
          {field.label}
        </label>
        <Input
          id={fieldId}
          type="password"
          autoComplete="off"
          placeholder={hasStoredValue ? 'Value is set — enter a new value to replace it' : 'Not set'}
          value={touched && typeof value === 'string' ? value : ''}
          onChange={(e) => {
            onTouch();
            onChange(e.target.value);
          }}
        />
        {field.help_text && <p className="text-sm text-steel">{field.help_text}</p>}
      </div>
    );
  }

  // "text" and any unrecognized type fall back to a plain text input.
  const currentValue = typeof value === 'string' ? value : (field.default as string | undefined) || '';
  return (
    <div className="space-y-2">
      <label htmlFor={fieldId} className="text-sm font-medium">
        {field.label}
      </label>
      <Input id={fieldId} type="text" value={currentValue} onChange={(e) => onChange(e.target.value)} />
      {field.help_text && <p className="text-sm text-steel">{field.help_text}</p>}
    </div>
  );
}
