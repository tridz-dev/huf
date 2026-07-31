import { useEffect, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  getElevenlabsSettings,
  updateElevenlabsSettings,
  getGroqSettings,
  updateGroqSettings,
  getOpenAISettings,
  updateOpenAISettings,
} from '@/services/voiceSettingsApi';
import { getProviders } from '@/services/providerApi';
import type { AIProvider } from '@/types/agent.types';
import type { ElevenlabsSettingsDoc, HttpProviderSettingsDoc } from '@/types/integration.types';
import { settleAll } from '@/lib/settleAll';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

export { VoiceSettingsTab };
export default VoiceSettingsTab;

function isValidUrl(value: string): boolean {
  if (!value) return true;
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
}

function HttpProviderForm({
  title,
  description,
  value,
  onSave,
  providers,
  notice,
}: {
  title: string;
  description: string;
  value: HttpProviderSettingsDoc;
  onSave: (data: HttpProviderSettingsDoc) => Promise<void>;
  providers: AIProvider[];
  notice?: ReactNode;
}) {
  const [form, setForm] = useState<HttpProviderSettingsDoc>(value);
  const [saving, setSaving] = useState(false);
  const urlError = form.api_url && !isValidUrl(form.api_url);

  useEffect(() => setForm(value), [value]);

  const handleSave = async () => {
    if (urlError) {
      toast.error('Enter a valid API URL');
      return;
    }
    setSaving(true);
    try {
      await onSave(form);
      toast.success(`${title} saved`);
    } catch {
      // handleFrappeError in the service already surfaces a toast
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {notice && (
        <CardContent className="pt-0 pb-2">
          <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
            {notice}
          </div>
        </CardContent>
      )}
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="flex items-center justify-between rounded-lg border p-4 sm:col-span-2">
          <div className="space-y-0.5">
            <Label>Enabled</Label>
            <p className="text-sm text-muted-foreground">Turn this provider on or off for transcription.</p>
          </div>
          <Switch
            checked={!!form.enabled}
            onCheckedChange={(checked) => setForm((f) => ({ ...f, enabled: checked ? 1 : 0 }))}
          />
        </div>

        <div className="space-y-2">
          <Label>Provider</Label>
          <Select
            value={form.provider || ''}
            onValueChange={(v) => setForm((f) => ({ ...f, provider: v || undefined }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select AI Provider" />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.provider_name || p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Model</Label>
          <Input
            value={form.model || ''}
            onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
            placeholder="whisper-large-v3"
          />
        </div>

        <div className="space-y-2 sm:col-span-2">
          <Label>API URL</Label>
          <Input
            value={form.api_url || ''}
            onChange={(e) => setForm((f) => ({ ...f, api_url: e.target.value }))}
            placeholder="https://api.example.com/v1/audio/transcriptions"
          />
          {urlError && <p className="text-sm text-destructive">Enter a valid URL.</p>}
        </div>

        <div className="space-y-2">
          <Label>Method</Label>
          <Select
            value={form.method || 'POST'}
            onValueChange={(v) => setForm((f) => ({ ...f, method: v as 'POST' | 'GET' }))}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="POST">POST</SelectItem>
              <SelectItem value="GET">GET</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Auth Type</Label>
          <Select
            value={form.auth_type || 'Bearer Token'}
            onValueChange={(v) => setForm((f) => ({ ...f, auth_type: v as 'Bearer Token' | 'API Key Header' | 'None' }))}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Bearer Token">Bearer Token</SelectItem>
              <SelectItem value="API Key Header">API Key Header</SelectItem>
              <SelectItem value="None">None</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>File Param</Label>
          <Input
            value={form.file_param || ''}
            onChange={(e) => setForm((f) => ({ ...f, file_param: e.target.value }))}
            placeholder="file"
          />
        </div>

        <div className="space-y-2">
          <Label>Response Path</Label>
          <Input
            value={form.response_path || ''}
            onChange={(e) => setForm((f) => ({ ...f, response_path: e.target.value }))}
            placeholder="text"
          />
        </div>
      </CardContent>
      <div className="flex justify-end p-6 pt-0">
        <Button onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          Save
        </Button>
      </div>
    </Card>
  );
}

function ElevenlabsForm({
  value,
  onSave,
  providers,
}: {
  value: ElevenlabsSettingsDoc;
  onSave: (data: ElevenlabsSettingsDoc) => Promise<void>;
  providers: AIProvider[];
}) {
  const [form, setForm] = useState<ElevenlabsSettingsDoc>(value);
  const [saving, setSaving] = useState(false);

  useEffect(() => setForm(value), [value]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(form);
      toast.success('Elevenlabs settings saved');
    } catch {
      // handleFrappeError in the service already surfaces a toast
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Elevenlabs</CardTitle>
        <CardDescription>Configure the Elevenlabs Conversational AI agent used for voice chat.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>Provider</Label>
          <Select
            value={form.provider || ''}
            onValueChange={(v) => setForm((f) => ({ ...f, provider: v || undefined }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select AI Provider" />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.provider_name || p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Agent ID</Label>
          <Input
            value={form.agent_id || ''}
            onChange={(e) => setForm((f) => ({ ...f, agent_id: e.target.value }))}
            placeholder="agent_xxxxxxxx"
          />
        </div>

        <div className="space-y-2 sm:col-span-2">
          <Label>Webhook Secret</Label>
          <Input
            type="password"
            autoComplete="off"
            value={form.webhook_secret || ''}
            onChange={(e) => setForm((f) => ({ ...f, webhook_secret: e.target.value }))}
            placeholder="Leave blank to keep existing value"
          />
        </div>
      </CardContent>
      <div className="flex justify-end p-6 pt-0">
        <Button onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          Save
        </Button>
      </div>
    </Card>
  );
}

function VoiceSettingsTab() {
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [openai, setOpenai] = useState<HttpProviderSettingsDoc>({});
  const [groq, setGroq] = useState<HttpProviderSettingsDoc>({});
  const [elevenlabs, setElevenlabs] = useState<ElevenlabsSettingsDoc>({});

  useEffect(() => {
    (async () => {
      setLoading(true);
      const errorLabels = ['providers', 'OpenAI settings', 'Groq settings', 'ElevenLabs settings'];
      const [providersRes, openaiRes, groqRes, elevenlabsRes] = await settleAll(
        [getProviders(), getOpenAISettings(), getGroqSettings(), getElevenlabsSettings()],
        (index, error) => {
          toast.error(`Failed to load ${errorLabels[index]}: ${getFrappeErrorMessage(error)}`);
        },
      );
      if (providersRes) {
        setProviders(Array.isArray(providersRes) ? providersRes : providersRes.items);
      }
      if (openaiRes) setOpenai(openaiRes);
      if (groqRes) setGroq(groqRes);
      if (elevenlabsRes) setElevenlabs(elevenlabsRes);
      setLoading(false);
    })();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl space-y-6">
        <p className="text-sm text-muted-foreground">
          Configure speech-to-text and voice agent providers used across HUF.
        </p>

        <Tabs defaultValue="openai">
          <TabsList>
            <TabsTrigger value="openai">OpenAI</TabsTrigger>
            <TabsTrigger value="groq">Groq</TabsTrigger>
            <TabsTrigger value="elevenlabs">Elevenlabs</TabsTrigger>
          </TabsList>

          <TabsContent value="openai" className="mt-4">
            <HttpProviderForm
              title="OpenAI"
              description="Configure OpenAI-compatible speech-to-text transcription."
              value={openai}
              onSave={async (data) => {
                await updateOpenAISettings(data);
                setOpenai(data);
              }}
              providers={providers}
              notice="Provider-specific transcription settings are deprecated. Configure an AI Provider and use Agent STT Model instead."
            />
          </TabsContent>

          <TabsContent value="groq" className="mt-4">
            <HttpProviderForm
              title="Groq"
              description="Configure Groq-hosted speech-to-text transcription."
              value={groq}
              onSave={async (data) => {
                await updateGroqSettings(data);
                setGroq(data);
              }}
              providers={providers}
              notice="Provider-specific transcription settings are deprecated. Configure an AI Provider and use Agent STT Model instead."
            />
          </TabsContent>

          <TabsContent value="elevenlabs" className="mt-4">
            <ElevenlabsForm
              value={elevenlabs}
              onSave={async (data) => {
                await updateElevenlabsSettings(data);
                setElevenlabs(data);
              }}
              providers={providers}
            />
          </TabsContent>
        </Tabs>
    </div>
  );
}
